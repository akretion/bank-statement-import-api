# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from markupsafe import Markup

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare
from odoo.tools.misc import format_amount, format_date

logger = logging.getLogger(__name__)
TAX_DECIMAL_DIGITS = 4


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    in_invoice_expense_categ_id = fields.Many2one(
        "account.bank.statement.expense.categ",
        ondelete="restrict",
        string="Expense Category",
    )
    in_invoice_account_id = fields.Many2one(
        "account.account",
        compute="_compute_in_invoice_account_id",
        store=True,
        readonly=False,
        precompute=True,
        string="Expense Account",
        check_company=True,
    )
    in_invoice_analytic_distribution = fields.Json(
        string="Analytic",
        compute="_compute_in_invoice_analytic_distribution",
        readonly=False,
        store=True,
        precompute=True,
    )
    analytic_precision = fields.Integer(
        default=lambda self: self.env["decimal.precision"].precision_get(
            "Percentage Analytic"
        ),
    )
    in_invoice_vat_rate = fields.Float(
        string="VAT Rate", digits=(16, TAX_DECIMAL_DIGITS), readonly=True
    )  # VAT 20% -> value = 20.0
    # Idea : we could decide that in_invoice_vat_amount is always positive:
    # - simpler for the user
    # - avoid sign errors
    in_invoice_tax_ids = fields.Many2many(
        "account.tax",
        check_company=True,
        domain="[('company_id', '=', company_id), ('type_tax_use', '=', 'purchase')]",
        string="Taxes",
    )
    in_invoice_vat_amount = fields.Monetary(
        string="VAT Amount",
        help="To make things easier for users, the VAT Amount is always positive.",
    )
    in_invoice_expense_description = fields.Char(string="Expense Description")
    in_invoice_force_invoice_date = fields.Date(string="Force Invoice Date")
    in_invoice_card_id = fields.Many2one(
        "account.bank.statement.card", string="Payment Card"
    )
    in_invoice_receipt_lost = fields.Boolean(string="Receipt Lost")
    in_invoice_show_button = fields.Boolean(
        compute="_compute_in_invoice_show_button",
        string="Show Button to Create Vendor Bill",
    )
    in_invoice_id = fields.Many2one(
        "account.move",
        string="Vendor Bill Created from Statement Line",
        check_company=True,
        readonly=True,
    )
    # in_invoice_country_id = fields.Many2one('res.country')

    _sql_constraints = [
        (
            "in_invoice_vat_amount_positive",
            "CHECK(in_invoice_vat_amount >= 0)",
            "The value of the field VAT Amount must be always positive.",
        )
    ]

    @api.depends(
        "company_id",
        "in_invoice_expense_categ_id",
        "in_invoice_card_id",
        "in_invoice_id",
    )
    def _compute_in_invoice_account_id(self):
        for line in self:
            account = False
            if (
                line.in_invoice_expense_categ_id
                and line.company_id
                and not line.in_invoice_id
            ):
                if line.in_invoice_card_id:
                    for (
                        card_account
                    ) in line.in_invoice_expense_categ_id.card_account_ids:
                        if card_account.card_id == line.in_invoice_card_id:
                            account = card_account.account_id
                if not account:
                    account = line.with_company(
                        line.company_id.id
                    ).in_invoice_expense_categ_id.account_id
            line.in_invoice_account_id = account

    @api.depends(
        "in_invoice_receipt_lost",
        "attachment_ids",
        "in_invoice_expense_description",
        "in_invoice_account_id",
    )
    def _compute_in_invoice_show_button(self):
        for line in self:
            show_button = False
            if (
                line.in_invoice_account_id
                and line.in_invoice_expense_description
                and (line.attachment_ids or line.in_invoice_receipt_lost)
            ):
                show_button = True
            line.in_invoice_show_button = show_button

    @api.depends("partner_id", "in_invoice_account_id")
    def _compute_in_invoice_analytic_distribution(self):
        for line in self:
            distribution = self.env[
                "account.analytic.distribution.model"
            ]._get_distribution(
                {
                    "partner_id": line.partner_id.id,
                    "partner_category_id": line.partner_id.category_id.ids,
                    "account_prefix": line.in_invoice_account_id.code,
                    "company_id": line.company_id.id,
                }
            )
            line.in_invoice_analytic_distribution = (
                distribution or line.in_invoice_analytic_distribution
            )

    @api.constrains("in_invoice_vat_rate")
    def _check_in_invoice_vat_rate(self):
        for line in self:
            if (
                line.in_invoice_vat_rate
                and float_compare(
                    line.in_invoice_vat_rate, 0, precision_digits=TAX_DECIMAL_DIGITS
                )
                < 0
            ):
                raise ValidationError(
                    _("The VAT rate (%s %%) must be positive.")
                    % line.in_invoice_vat_rate
                )

    def in_invoice_create_disabled(self):
        self.ensure_one()

    def in_invoice_create(self):
        self.ensure_one()
        logger.info("Start Vendor Bill")
        vals = self._prepare_in_invoice()
        inv = self.env["account.move"].create(vals)
        logger.info("Vendor bill created from statement line %s", inv.display_name)
        if self.attachment_ids:
            self.attachment_ids.write(
                {
                    "res_id": inv.id,
                }
            )
        inv.message_post(
            body=Markup(
                _(
                    "Vendor bill created from the bank statement line "
                    "<a href=# data-oe-model=account.bank.statement.line "
                    "data-oe-id=%(st_line_id)s>%(st_line_name)s</a>",
                    st_line_id=self.id,
                    st_line_name=self.display_name,
                )
            )
        )
        inv.with_context(validate_analytic=True)._post(soft=False)
        self._in_invoice_post_process(inv)
        stvals = {"in_invoice_id": inv.id, "can_reconcile": True}
        if not self.partner_id:
            stvals["partner_id"] = vals["partner_id"]
        new_data = []
        for line in self.reconcile_data_info["data"]:
            new_data.append(line)
        for line in inv.line_ids.filtered(
            lambda x: x.account_id == inv.partner_id.property_account_payable_id
        ):
            reconcile_auxiliary_id, lines = self._get_reconcile_line(
                line, "other", True, 0.0
            )
            new_data += lines
        data_info = self._recompute_suspense_line(
            new_data,
            self.reconcile_data_info["reconcile_auxiliary_id"],
            self.manual_reference,
        )
        self.write(stvals)
        self.reconcile_data_info = data_info
        self.reconcile_bank_line()  # button "Validate"
        logger.info("End Vendor Bill")

    def _in_invoice_post_process(self, invoice):
        cur = self.currency_id
        total = abs(self.amount)
        ini_vat_amount = invoice.amount_tax
        invoice._check_total_amount(total)
        if self.currency_id.compare_amounts(invoice.amount_total, total):
            raise UserError(
                _(
                    "Wrong total amount. Transaction total amount: %(trans_total)s. "
                    "Vendor bill/refund total amount: %(invoice_total)s. "
                    "This should never happen.",
                    trans_total=format_amount(self.env, total, cur),
                    invoice_total=format_amount(self.env, invoice.amount_total, cur),
                )
            )
        if cur.compare_amounts(invoice.amount_tax, self.in_invoice_vat_amount):
            raise UserError(
                _(
                    "Wrong tax amount. Maybe the code to force the tax amount didn't work. "
                    "This should never happen."
                )
            )
        invoice.message_post(
            body=_(
                "Total VAT Amount has been forced from %(ini_vat_amount)s to %(vat_amount)s.",
                ini_vat_amount=format_amount(self.env, ini_vat_amount, cur),
                vat_amount=format_amount(self.env, invoice.amount_tax, cur),
            )
        )

    def _prepare_in_invoice(self):
        self.ensure_one()
        if self.currency_id.compare_amounts(self.amount, 0) <= 0:
            move_type = "in_invoice"
            total = self.amount * -1
        else:
            move_type = "in_refund"
            total = self.amount
        untaxed = self.currency_id.round(total - self.in_invoice_vat_amount)
        partner = self.partner_id or self.company_id.misc_partner_id
        if not partner:
            raise UserError(
                _(
                    "No partner on the bank statement line and no misc partner "
                    "on the accounting configuration page of company '%s'."
                )
                % self.company_id.name
            )
        partner = partner.with_company(self.company_id.id)
        vat_compare = self.company_currency_id.compare_amounts(
            self.in_invoice_vat_amount, 0
        )
        assert vat_compare >= 0
        if vat_compare > 0 and not self.in_invoice_tax_ids:
            raise UserError(
                _("The VAT amount is not null (%s), so you must select a tax.")
                % format_amount(
                    self.env, self.in_invoice_vat_amount, self.company_currency_id
                )
            )
        self.company_currency_id.compare_amounts(self.amount, 0)

        lvals = {
            "display_type": "product",
            "name": self.in_invoice_expense_description,
            "account_id": self.in_invoice_account_id.id,
            "analytic_distribution": self.in_invoice_analytic_distribution,
            "quantity": 1,
            "price_unit": untaxed,
            "tax_ids": [Command.set(self.in_invoice_tax_ids.ids)],
        }
        journal = self.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", self.company_id.id)],
            limit=1,
        )
        if not journal:
            raise UserError(
                _("No purchase journal in company '%s'.") % self.company_id.name
            )
        today = fields.Date.context_today(self)
        if (
            self.in_invoice_force_invoice_date
            and self.in_invoice_force_invoice_date > today
        ):
            raise UserError(
                _("The Force Invoice Date (%s) is in the future!")
                % format_date(self.env, self.in_invoice_force_invoice_date)
            )
        vals = {
            "move_type": move_type,
            "company_id": self.company_id.id,
            "journal_id": journal.id,
            "invoice_date": self.in_invoice_force_invoice_date or self.date,
            "partner_id": partner.id,
            "currency_id": self.currency_id.id,
            "invoice_line_ids": [Command.create(lvals)],
        }
        if not partner.property_supplier_payment_term_id:
            vals["invoice_date_due"] = vals["invoice_date"]
        return vals
