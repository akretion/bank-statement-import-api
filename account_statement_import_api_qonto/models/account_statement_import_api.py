# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import requests

from odoo import _, api, fields, models

from .account_journal import BASE_URL, TIMEOUT

logger = logging.getLogger(__name__)


class AccountStatementImportApi(models.Model):
    _inherit = "account.statement.import.api"

    service = fields.Selection(ondelete={"qonto": "cascade"})

    @api.model
    def _get_service_info(self):
        service2info = super()._get_service_info()
        service2info["qonto"] = {
            "name": "Qonto",
            "company_required": True,
            "login_required": True,
            "password_required": True,
            "user_company_required": False,
            "show_backward_days": False,
            "instructions": _(
                "<p>Go to the web interface of your "
                '<a href="https://qonto.com/">Qonto</a> account. '
                "On the left panel, click on <strong>Integrations and "
                "Partnerships</strong> and then click on <strong>API Keys</strong>:</p>"
                "<ul><li>Copy the <strong>Identifier</strong> to the field "
                "<em>Login or Client ID</em></li>"
                "<li>Copy the <strong>Secret Key</strong> to the field "
                "<em>Password or Client Secret</em></li></ul>"
                "<p>Then, click on the button <em>Test API</em> to test that "
                "Odoo is able to query the Qonto API.</p>"
            ),
        }
        return service2info

    def _prepare_speedy(self):
        self.ensure_one()
        speedy = super()._prepare_speedy()
        if self.service == "qonto":
            speedy.update(
                {
                    "headers": {
                        "Authorization": f"{speedy['login']}:{speedy['password']}"
                    },
                    "update_existing_bank_statement_lines": True,
                }
            )
        return speedy

    def _qonto_test_api(self, result, speedy):
        self.ensure_one()
        self._qonto_get_all_pages("bank_accounts", result, speedy)

    def _update_api_accounts_qonto(self, result, speedy):
        self.ensure_one()
        accounts = self._qonto_get_all_pages("bank_accounts", result, speedy)
        res = []
        for account in accounts:
            res.append(
                {
                    "name": account["name"],
                    "account_number": account.get("iban"),
                    "bank_name": account.get("bic"),
                    "identifier": account["id"],
                    "company_id": self.company_id.id,
                    "currency_code": account.get("currency"),
                }
            )
        return res

    @api.model
    def _qonto_get_all_pages(self, api_name, result, speedy, params=None):
        ajo = self.env["account.journal"]
        url = BASE_URL + api_name
        if params is None:
            params = {}
        params["page"] = 1
        # 'per_page' is set by default to the maximum (100), cf
        # https://docs.qonto.com/get-started/general/pagination
        total_pages = 1
        data = []
        while params["page"] <= total_pages:
            try:
                res = requests.get(
                    url,
                    verify=True,
                    headers=speedy["headers"],
                    params=params,
                    timeout=TIMEOUT,
                )
            except Exception as e:
                ajo._api_import_error_log(
                    result, f"API call on {url} with params={params} failed: {e}"
                )
                return []
            if res.status_code != 200:
                ajo._api_import_error_log(
                    result,
                    f"API call on {url} with params={params} returned an "
                    f"HTTP error code {res.status_code}.",
                )
                return []
            res_json = res.json()
            total_pages = res_json["meta"]["total_pages"]
            data += res_json.get(api_name, [])
            params["page"] += 1
        return data
