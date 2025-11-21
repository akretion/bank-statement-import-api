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

    company_id = fields.Many2one("res.company", required=True, ondelete="cascade")
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
        res.update(
            {
                "company_id": self.env.company.id,
                "statement_import_api_id": import_api_id,
            }
        )
        return res

    def run(self):
        self.ensure_one()
        import_api = self.statement_import_api_id
        service = import_api.service
        method_name = f"_{service}_create_user"
        speedy = import_api._prepare_speedy()
        result = {"logs": []}
        if self.company_id.id in speedy["company_id2user_identifier"]:
            raise UserError(
                _(
                    "On bank statement import API '%(import_api)s', "
                    "a user already exists in company '%(company)s'.",
                    import_api=import_api.display_name,
                    company=self.company_id.name,
                )
            )
        method = getattr(import_api, method_name)
        company_user_vals = method(self.company_id, result, speedy)
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
        if not company_user_vals:
            raise UserError(
                _(
                    "The method %s didn't return anything and didn't generate "
                    "any error. THis should never happen."
                )
                % method_name
            )
        company_user_vals.update(
            {
                "company_id": self.company_id.id,
                "statement_import_api_id": import_api.id,
            }
        )
        company_user = self.env["account.statement.import.api.company.user"].create(
            company_user_vals
        )
        logger.info("Company User ID %d created", company_user.id)
