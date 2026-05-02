# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

logger = logging.getLogger(__name__)


class AccountStatementImportApiDeleteUser(models.TransientModel):
    _name = "account.statement.import.api.delete.user"
    _description = "Wizard to delete a user"

    statement_import_api_id = fields.Many2one(
        "account.statement.import.api",
        readonly=True,
        required=True,
        string="Bank Statement Import API",
    )
    confirm = fields.Boolean(string="Do you confirm?")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        assert self._context.get("active_model") == "account.statement.import.api"
        import_api_id = self._context.get("active_id")
        res["statement_import_api_id"] = import_api_id
        return res

    def run(self):
        self.ensure_one()
        if not self.confirm:
            raise UserError(
                _("You must confirm the deletion of the user or cancel the operation.")
            )
        import_api = self.statement_import_api_id
        # first, we try to delete API bank accounts
        logger.info("Deleting API bank account IDs %s", import_api.api_account_ids.ids)
        import_api.api_account_ids.unlink()
        import_api.connector_ids.unlink()
        speedy = import_api._prepare_speedy()
        method_name = f"_{speedy['service']}_delete_user"
        result = {"logs": []}
        method = getattr(import_api, method_name)
        method(result, speedy)
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
        logger.info(
            "Deleting user identifier %s on statement import API %s ID %d",
            import_api.user_identifier,
            import_api.display_name,
            import_api.id,
        )
        import_api.write(import_api._prepare_delete_user())
