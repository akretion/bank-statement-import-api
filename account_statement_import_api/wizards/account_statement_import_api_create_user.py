# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

logger = logging.getLogger(__name__)


class AccountStatementImportApiCreateUser(models.TransientModel):
    _name = "account.statement.import.api.create.user"
    _description = "Wizard to create a new user"

    statement_import_api_id = fields.Many2one(
        "account.statement.import.api",
        readonly=True,
        string="Bank Statement Import API",
    )
    service = fields.Selection(related="statement_import_api_id.service")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        assert self._context.get("active_model") == "account.statement.import.api"
        import_api_id = self._context.get("active_id")
        res["statement_import_api_id"] = import_api_id
        return res

    def run(self):
        self.ensure_one()
        import_api = self.statement_import_api_id
        assert not import_api.user_identifier
        service = import_api.service
        method_name = f"_{service}_create_user"
        speedy = import_api.with_context(
            no_check_user_identifier=True
        )._prepare_speedy()
        result = {"logs": []}
        method = getattr(self, method_name)
        vals = method(result, speedy)
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
        if not vals:
            raise UserError(
                _(
                    "The method %s didn't return anything and didn't generate "
                    "any error. This should never happen.",
                    method_name,
                )
            )
        if not vals.get("user_identifier"):
            raise UserError(
                _(
                    "The method %s didn't return a user identifier and didn't generate "
                    "any error. This should never happen.",
                    method_name,
                )
            )
        import_api.write(vals)
