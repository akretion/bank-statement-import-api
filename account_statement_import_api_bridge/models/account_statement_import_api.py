# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

BRIDGE_VERSION = "2025-01-15"
BRIDGE_BASE_URL = "https://api.bridgeapi.io"
BRIDGE_API_VERSION = "v3"
BRIDGE_MAX_PAGE_LIMIT = 500
TIMEOUT = 20


logger = logging.getLogger(__name__)


class AccountStatementImportApi(models.Model):
    _inherit = "account.statement.import.api"

    service = fields.Selection(ondelete={"bridge": "cascade"})

    @api.model
    def _get_service_info(self):
        service2info = super()._get_service_info()
        service2info["bridge"] = {
            "name": "BridgeAPI.io",
            "company_required": False,
            "login_required": True,
            "password_required": True,
            "user_company_required": True,
            "show_backward_days": True,
            # "instructions": _("TODO Write instructions"),
        }
        return service2info

    def _bridge_get_token(self, company, result, speedy):
        if not speedy["company_id2token"].get(company.id):
            token = self._bridge_get_new_token(company, result, speedy)
            # at this stage, token can be None
            speedy["company_id2token"][company.id] = token
        return speedy["company_id2token"][company.id]

    def _bridge_get_headers(self, company, result, speedy):
        token = self._bridge_get_token(company, result, speedy)
        if not token:
            return None
        headers = {
            "Bridge-Version": BRIDGE_VERSION,
            "accept": "application/json",
            "content-type": "application/json",
            "Authorization": "Bearer %s" % token,
            "Client-Id": self.login,
            "Client-Secret": self.password,
        }
        return headers

    def _bridge_get_new_token(self, company, result, speedy):
        assert company
        ajo = self.env["account.journal"]
        headers_token = {
            "Bridge-Version": BRIDGE_VERSION,
            "Client-Id": self.login,
            "Client-Secret": self.password,
            "accept": "application/json",
            "content-type": "application/json",
        }
        external_user_identifier = speedy["company_id2user_identifier"].get(company.id)
        if not external_user_identifier:
            raise UserError(
                _(
                    "On bank statement import API '%(import_api)s', "
                    "missing Bridge External User Identifier for company '%(company)s'.",
                    import_api=self.display_name,
                    company=company.display_name,
                )
            )
        post_json = {"external_user_id": external_user_identifier}
        url = f"{BRIDGE_BASE_URL}/v3/aggregation/authorization/token"
        try:
            token_res = requests.post(
                url, headers=headers_token, json=post_json, timeout=TIMEOUT
            )
        except Exception as e:
            ajo._api_import_error_log(
                result,
                f"API call on {url} failed: {e}. "
                f"Could not get a token for company {company.name}.",
            )
            return None
        if token_res.status_code != 200:
            ajo._api_import_error_log(
                result,
                f"API call on {url} return an HTTP error code "
                f"{token_res.status_code}. Could not get a token for "
                f"company {company.name}.",
            )
            return None
        token_dict = token_res.json()
        token = token_dict["access_token"]
        ajo._api_import_info_log(
            result,
            f"Successful API call on {url} to get a new token "
            f"for company {company.name}",
        )
        logger.debug(
            "New Bridge API session token %s for company %s (user: %s)",
            token,
            company.name,
            external_user_identifier,
        )
        return token

    def _bridge_test_api(self, result, speedy):
        self.ensure_one()
        company = self.company_id or self.env.company
        self._bridge_get_new_token(company, result, speedy)

    def _update_api_accounts_bridge(self, result, speedy):
        self.ensure_one()
        company = self.company_id or self.env.company
        headers = self._bridge_get_headers(company, result, speedy)
        if not headers:
            return None
        providers = self._bridge_get_all_pages("providers", headers, result)
        if providers is None:
            return None
        providers_id2name = {}
        for provider in providers:
            providers_id2name[provider["id"]] = provider["name"]

        bridge_accounts = self._bridge_get_all_pages(
            "aggregation/accounts", headers, result
        )
        res = []
        for account in bridge_accounts or []:
            res.append(
                {
                    "name": account["name"],
                    "account_type": account.get("type"),
                    "account_number": account.get("iban"),
                    "bank_name": providers_id2name.get(account.get("provider_id")),
                    "currency_code": account.get("currency_code"),
                    "identifier": account["id"],
                    "company_id": company.id,
                }
            )
        return res

    @api.model
    def _bridge_get_all_pages(self, api_name, headers, result, params=None):
        ajo = self.env["account.journal"]
        url = f"{BRIDGE_BASE_URL}/{BRIDGE_API_VERSION}/{api_name}"
        if params is None:
            params = {}
        if not params.get("limit"):
            params["limit"] = BRIDGE_MAX_PAGE_LIMIT
        try:
            res = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        except Exception as e:
            ajo._api_import_error_log(
                result, f"API call on {url} with params={params} failed: {e}"
            )
            return None
        if res.status_code != 200:
            ajo._api_import_error_log(
                result,
                f"API call on {url} with params={params} returned an "
                f"HTTP error code {res.status_code}.",
            )
            return None
        ajo._api_import_info_log(
            result, f"Successful API call on {url} with params={params}"
        )
        res_dict = res.json()
        res_list = res_dict["resources"]
        next_uri = res_dict["pagination"].get("next_uri")
        page = 1
        while next_uri:
            page += 1
            url = f"{BRIDGE_BASE_URL}{next_uri}"
            try:
                res_next_page = requests.get(url, headers=headers, timeout=TIMEOUT)
            except Exception as e:
                ajo._api_import_error_log(
                    result, f"API call on {url} failed (page {page}): {e}"
                )
                return None
            if res_next_page.status_code != 200:
                ajo._api_import_error_log(
                    result,
                    f"API call on {url} returned an "
                    f"HTTP error code {res_next_page.status_code} (page {page}).",
                )
                return None
            ajo._api_import_info_log(
                result, f"Successful API call on {url} (page {page})"
            )
            res_next_page_dict = res_next_page.json()
            res_list += res_next_page_dict["resources"]
            next_uri = res_next_page_dict["pagination"].get("next_uri")
        return res_list
