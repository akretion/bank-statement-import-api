# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


from odoo import _, api, fields, models


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    in_invoice_analytic_account_ids = fields.Many2many(
        comodel_name="account.bank.statement.analytic.account",
        relation="in_invoice_analytic_account_rel",
        string="Analytic accounts",
    )
    warn_message = fields.Char(compute="_compute_warning_message")

    @api.depends(
        "partner_id",
        "in_invoice_account_id",
        "in_invoice_analytic_account_ids",
        "in_invoice_analytic_account_ids.analytic_account_id",
    )
    def _compute_in_invoice_analytic_distribution(self):
        default_lines = self
        for line in self:
            distribution = {}
            for analytic_account in line.in_invoice_analytic_account_ids.filtered(
                "analytic_account_id"
            ):
                distribution[str(analytic_account.analytic_account_id.id)] = 100
            line.in_invoice_analytic_distribution = distribution
            if distribution:
                default_lines -= line
        if default_lines:
            return super(
                AccountBankStatementLine, default_lines
            )._compute_in_invoice_analytic_distribution()

    @api.depends(
        "in_invoice_analytic_account_ids",
        "in_invoice_analytic_account_ids.analytic_account_id",
    )
    def _compute_warning_message(self):
        for line in self:
            message = False
            missing_analytic = line.in_invoice_analytic_account_ids.filtered(
                lambda x: not x.analytic_account_id
            )
            if missing_analytic:
                message = _(
                    "Missing mapping for analytic account(s) : %s",
                    ", ".join(missing_analytic.mapped("name")),
                )
            line.warn_message = message
