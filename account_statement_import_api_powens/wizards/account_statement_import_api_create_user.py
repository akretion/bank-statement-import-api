# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class AccountStatementImportApiCreateUser(models.TransientModel):
    _inherit = "account.statement.import.api.create.user"

    def _powens_create_user(self, result, speedy):
        ajo = self.env["account.journal"]
        headers = {
            "content-type": "application/json",
        }

        json_dict = {
            "client_id": speedy["login"],
            "client_secret": speedy["password"],
        }
        res = self._powens_post("auth/init", headers, json_dict, result)
        if res.get("type") != "permanent" or not res.get("auth_token"):
            ajo._api_import_error_log(
                result,
                f"The API call didn't return a permanent token as expected. "
                f"Token type returned was '{res.get('type')}'.",
            )
            return None
        if not res.get("id_user"):
            ajo._api_import_error_log(
                result,
                "The API call to create a company user didn't return a user ID as expected.",
            )
            return None
        company_user_vals = {
            "identifier": res["id_user"],
            "powens_token": res["auth_token"],
        }
        return company_user_vals
