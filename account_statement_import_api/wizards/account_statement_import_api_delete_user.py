# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

logger = logging.getLogger(__name__)


class AccountStatementImportApiDeleteUser(models.TransientModel):
    _name = "account.statement.import.api.delete.user"
    _description = "Wizard to delete a user"

    company_user_id = fields.Many2one(
        "account.statement.import.api.company.user", string="Per-Company User"
    )
    company_id = fields.Many2one(related="company_user_id.company_id")
    statement_import_api_id = fields.Many2one(
        related="company_user_id.statement_import_api_id"
    )

    def run(self):
        self.ensure_one()
        company_user = self.company_user_id
        if not company_user:
            raise UserError(_("Company User is not set."))
        import_api = self.statement_import_api_id
        # first, we try to delete API bank accounts
        api_bank_accounts = (
            self.env["account.statement.import.api.account"]
            .with_context(active_test=False)
            .search(
                [
                    ("company_id", "=", company_user.company_id.id),
                    (
                        "statement_import_api_id",
                        "=",
                        company_user.statement_import_api_id.id,
                    ),
                ]
            )
        )
        logger.info("Deleting API bank account IDs %s", api_bank_accounts.ids)
        api_bank_accounts.unlink()
        # TODO delete connectors ?
        speedy = import_api._prepare_speedy()
        method_name = f"_{speedy['service']}_delete_user"
        result = {"logs": []}
        method = getattr(company_user, method_name)
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
        logger.info("Deleting Company User ID %d...", company_user.id)
        company_user.unlink()
