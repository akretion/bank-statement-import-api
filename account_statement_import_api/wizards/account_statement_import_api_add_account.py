# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class AccountStatementImportApiAddAccount(models.TransientModel):
    _name = "account.statement.import.api.add.account"
    _description = "Add bank account(s) to statement import API"

    company_id = fields.Many2one("res.company", readonly=True)
    statement_import_api_id = fields.Many2one(
        "account.statement.import.api",
        readonly=True,
        string="Bank Statement Import API",
    )
    service = fields.Selection(related="statement_import_api_id.service")
    url = fields.Char(readonly=True, string="URL")
    state = fields.Selection(
        [
            ("start", "Start"),
            ("url", "URL"),
        ],
        readonly=True,
        default="start",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        assert self._context.get("active_model") == "account.statement.import.api"
        assert self._context.get("active_id")
        res.update(
            {
                "company_id": self.env.company.id,
                "statement_import_api_id": self._context["active_id"],
            }
        )
        return res

    def start2url(self):
        self.ensure_one()
        import_api = self.statement_import_api_id
        service = import_api.service
        method_name = f"_{service}_get_add_account_url"
        speedy = import_api._prepare_speedy()
        result = {"logs": []}
        method = getattr(import_api, method_name)
        url = method(self.company_id, result, speedy)
        self.write({"url": url, "state": "url"})
        action = self.env["ir.actions.actions"]._for_xml_id(
            "account_statement_import_api.account_statement_import_api_add_account_action"
        )
        action.update(
            {
                "res_id": self.id,
            }
        )
        return action

    def finish(self):
        self.ensure_one()
        action = self.statement_import_api_id.update_api_accounts()
        if action:
            action["params"]["next"] = {"type": "ir.actions.act_window_close"}
        return action
