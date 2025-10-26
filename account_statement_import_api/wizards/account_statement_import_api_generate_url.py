# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountStatementImportApiGenerateUrl(models.TransientModel):
    _name = "account.statement.import.api.generate.url"
    _description = "Wizard to generate a URL to manage the API bank account(s)"

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
    feature = fields.Selection(
        [
            ("add_account", "Add Account"),
            ("renew_auth", "Renew Authentication"),
            ("manage_accounts", "Manage Accounts"),
        ],
        required=True,
        readonly=True,
    )
    renew_auth_api_account_id = fields.Many2one(
        "account.statement.import.api.account",
        string="API Bank Account",
        domain="[('statement_import_api_id', '=', statement_import_api_id)]",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self._context.get("active_model") == "account.statement.import.api":
            import_api_id = self._context.get("active_id")
            assert res.get("feature") in ("add_account", "manage_accounts")
        elif (
            self._context.get("active_model") == "account.statement.import.api.account"
        ):
            res["renew_auth_api_account_id"] = self._context.get("active_id")
            assert res.get("feature") == "renew_auth"
            api_account = self.env["account.statement.import.api.account"].browse(
                res["renew_auth_api_account_id"]
            )
            import_api_id = api_account.statement_import_api_id.id
        res.update(
            {
                "company_id": self.env.company.id,
                "statement_import_api_id": import_api_id,
            }
        )
        return res

    def start2url(self):
        self.ensure_one()
        import_api = self.statement_import_api_id
        service = import_api.service
        if self.feature == "renew_auth" and not self.renew_auth_api_account_id:
            raise UserError(_("You must select an API Bank Account."))
        method_name = f"_{service}_{self.feature}_get_url"
        speedy = import_api._prepare_speedy()
        result = {"logs": []}
        method = getattr(import_api, method_name)
        if self.feature in ("add_account", "manage_accounts"):
            url = method(self.company_id, result, speedy)
        elif self.feature == "renew_auth":
            url = method(
                self.renew_auth_api_account_id, self.company_id, result, speedy
            )
        for log_type, msg in result["logs"]:
            if log_type == "error":
                raise UserError(
                    _(
                        "Failed to retreive the URL via the '%(service_name)s' API. "
                        "Error: %(msg)s",
                        service_name=speedy["service_info"]["name"],
                        msg=msg,
                    )
                )
        self.write({"url": url, "state": "url"})
        action = self.env["ir.actions.actions"]._for_xml_id(
            "account_statement_import_api.account_statement_import_api_generate_url_action"
        )
        action["res_id"] = self.id
        return action

    def finish(self):
        self.ensure_one()
        action = self.statement_import_api_id.update_api_accounts()
        if action:
            action["params"]["next"] = {"type": "ir.actions.act_window_close"}
        return action
