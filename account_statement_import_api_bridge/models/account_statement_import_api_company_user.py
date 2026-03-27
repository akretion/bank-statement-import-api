# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountStatementImportApiCompanyUser(models.Model):
    _inherit = "account.statement.import.api.company.user"

    bridge_external_identifier = fields.Char(string="Bridge API External Identifier")

    _sql_constraints = [
        (
            "bridge_external_identifier_unique",
            "unique(statement_import_api_id, bridge_external_identifier)",
            "This Bridge API external identifier is already used on this "
            "bank statement import API.",
        ),
    ]

    def _bridge_delete_user(self, result, speedy):
        self.ensure_one()
        headers = self.statement_import_api_id._bridge_get_headers_no_token(speedy)
        url_path = f"aggregation/users/{self.identifier}"
        res = self.env["account.statement.import.api"]._bridge_del(
            url_path, headers, result, speedy
        )
        return res
