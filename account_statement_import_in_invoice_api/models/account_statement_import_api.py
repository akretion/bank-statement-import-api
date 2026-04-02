# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from unidecode import unidecode

from odoo import _, api, fields, models
from odoo.exceptions import UserError

logger = logging.getLogger(__name__)


class AccountStatementImportApi(models.Model):
    _inherit = "account.statement.import.api"

    show_analytic_button = fields.Boolean(compute="_compute_show_analytic")
    bank_statement_analytic_account_ids = fields.One2many(
        "account.bank.statement.analytic.account",
        "statement_import_api_id",
        string="Bank Statement Analytic Accounts",
    )
    bank_statement_analytic_account_count = fields.Integer(
        compute="_compute_bank_statement_analytic_account_count",
        string="Number of Bank Statement Analytic Accounts",
    )
    bank_statement_expense_categ_count = fields.Integer(
        compute="_compute_bank_statement_expense_categ_count",
        string="Number of Bank Statement Expense Categories",
    )

    @api.depends("service")
    def _compute_show_analytic(self):
        service2info = self._get_service_info()
        for record in self:
            show_analytic_button = False
            if record.service:
                info = service2info[record.service]
                show_analytic_button = info.get("show_analytic_button")
            record.show_analytic_button = show_analytic_button

    def _compute_bank_statement_analytic_account_count(self):
        rg_res = self.env["account.bank.statement.analytic.account"].read_group(
            [("statement_import_api_id", "in", self.ids)],
            ["statement_import_api_id"],
            ["statement_import_api_id"],
        )
        mapped_data = {
            x["statement_import_api_id"][0]: x["statement_import_api_id_count"]
            for x in rg_res
        }
        for rec in self:
            rec.bank_statement_analytic_account_count = mapped_data.get(rec.id, 0)

    def _compute_bank_statement_expense_categ_count(self):
        rg_res = self.env["account.bank.statement.expense.categ"].read_group(
            [("service", "!=", False)], ["service"], ["service"]
        )
        service2count = {x["service"]: x["service_count"] for x in rg_res}
        for rec in self:
            rec.bank_statement_expense_categ_count = service2count.get(rec.service, 0)

    def _prepare_speedy(self):
        speedy = super()._prepare_speedy()
        exp_categ_read = (
            self.env["account.bank.statement.expense.categ"]
            .with_context(active_test=False)
            .search_read([("service", "=", self.service)], ["code"])
        )
        expcateg_code2id = {x["code"]: x["id"] for x in exp_categ_read}
        speedy["expcateg_code2id"] = expcateg_code2id
        if not speedy["service_info"].get("show_analytic_button"):
            return speedy
        bs_analytic_account_read = (
            self.env["account.bank.statement.analytic.account"]
            .with_context(active_test=False)
            .search_read(
                [("statement_import_api_id", "=", self.id)],
                [
                    "identifier",
                    "analytic_account_id",
                    "name",
                    "display_name",
                ],
            )
        )
        bs_ana_acc_ident2vals = {
            x["identifier"]: {
                "id": x["id"],
                "analytic_account_id": x["analytic_account_id"]
                and x["analytic_account_id"][0]
                or False,
                "name": x["name"],
                "display_name": x["display_name"],
            }
            for x in bs_analytic_account_read
        }
        speedy["bs_analytic_account_ident2vals"] = bs_ana_acc_ident2vals
        return speedy

    def update_api_analytic_accounts(self):
        self.ensure_one()
        result = {"logs": []}
        speedy = self._prepare_speedy()
        method_name = f"_{self.service}_update_api_analytic_accounts"
        method = getattr(self, method_name)
        account_ident2vals = method(result, speedy)
        if not account_ident2vals:
            raise UserError(result["logs"][-1][1])
        to_create_vals_list = []
        # 1. clean-up
        for account_ident, vals in account_ident2vals.items():
            # clean-up vals
            for key, value in vals.items():
                if value and isinstance(value, str):
                    vals[key] = value.strip()
            if not account_ident:
                raise UserError(
                    _(
                        "Missing identifier for bank statement analytic account %s. "
                        "This should never happen.",
                        vals,
                    )
                )
            if not isinstance(account_ident, str):
                raise UserError(
                    _(
                        "Account identifier %(ident)s for bank statement analytic "
                        "account %(vals)s must be a string.",
                        ident=account_ident,
                        vals=vals,
                    )
                )
            if not vals.get("name"):
                raise UserError(
                    _(
                        "Missing 'name' for bank statement analytic account %s. This "
                        "should never happen.",
                        vals,
                    )
                )
            if not vals.get("parent_name"):
                raise UserError(
                    _(
                        "Missing 'parent name' for bank statement analytic account %s. "
                        "This should never happen.",
                        vals,
                    )
                )
        # 2. Update and orphan
        write_count = 0
        archive_count = 0
        for bs_ana_account in self.env[
            "account.bank.statement.analytic.account"
        ].search([("statement_import_api_id", "=", self.id)]):
            if bs_ana_account.identifier in account_ident2vals:
                vals = account_ident2vals[bs_ana_account.identifier]
                bs_ana_account.write(vals)
                logger.info(
                    "Bank statement analytic account %s ID %s updated",
                    bs_ana_account.display_name,
                    bs_ana_account.id,
                )
                account_ident2vals.pop(bs_ana_account.identifier)
                write_count += 1
            else:
                bs_ana_account.write({"active": False})
                logger.info(
                    "Bank statement analytic account %s archived",
                    bs_ana_account.display_name,
                )
                archive_count += 1

        # 3. Create
        message_list = []
        if account_ident2vals:
            to_create_vals_list = []
            ana_accounts = self.env["account.analytic.account"].search_read(
                [("company_id", "in", (False, self.company_id.id))], ["name"]
            )
            ana_account_name2id = {
                unidecode(x["name"].strip().lower()): x["id"] for x in ana_accounts
            }
            for account_ident, vals in account_ident2vals.items():
                simplified_name = unidecode(vals["name"].strip().lower())
                vals.update(
                    {
                        "identifier": account_ident,
                        "statement_import_api_id": self.id,
                        "analytic_account_id": ana_account_name2id.get(simplified_name),
                    }
                )
                to_create_vals_list.append(vals)
            if to_create_vals_list:
                self.env["account.bank.statement.analytic.account"].create(
                    to_create_vals_list
                )
                logger.info(
                    "%d bank statement analytic account(s) created on statement import "
                    "API %s",
                    len(to_create_vals_list),
                    self.display_name,
                )
                message_list.append(
                    _(
                        "%d bank statement analytic accounts created.",
                        len(to_create_vals_list),
                    )
                )

        if write_count:
            message_list.append(
                _("%d bank statement analytic accounts updated.", write_count)
            )
        if archive_count:
            message_list.append(
                _("%d bank statement analytic accounts archived.", archive_count)
            )
        action_next = self.env["ir.actions.actions"]._for_xml_id(
            "account_statement_import_api.account_statement_import_api_action"
        )
        action_next.update(
            {
                "views": [x for x in action_next["views"] if x and x[1] == "form"],
                "view_mode": "form",
                "res_id": self.id,
            }
        )
        action = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("Successful Update"),
                "message": "\n".join(message_list),
                "next": action_next,
            },
        }
        return action

    def action_view_analytic_account(self):
        action = self.env["ir.actions.actions"]._for_xml_id(
            "account_statement_import_in_invoice_api."
            "account_bank_statement_analytic_account_action"
        )
        action["context"] = {"active_test": True}
        action["domain"] = [("statement_import_api_id", "=", self.id)]
        return action

    def action_view_categ_expense(self):
        action = self.env["ir.actions.actions"]._for_xml_id(
            "account_statement_import_in_invoice.account_bank_statement_expense_categ_action"
        )
        action["context"] = {"active_test": True}
        action["domain"] = [("service", "=", self.service)]
        return action
