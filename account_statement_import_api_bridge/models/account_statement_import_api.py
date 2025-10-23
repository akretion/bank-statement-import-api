# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

BRIDGE_VERSION = "2025-01-15"
BRIDGE_BASE_URL = "https://api.bridgeapi.io"
BRIDGE_API_VERSION = "v3"
BRIDGE_MAX_PAGE_LIMIT = 500
TIMEOUT = 20


logger = logging.getLogger(__name__)


class AccountStatementImportApi(models.Model):
    _inherit = "account.statement.import.api"

    service = fields.Selection(
        selection_add=[
            ("bridge", "BridgeAPI.io"),
        ],
        ondelete={"bridge": "cascade"},
    )

    @api.constrains("service", "login", "password")
    def _check_bridge(self):
        for rec in self:
            if rec.service == "bridge":
                if not rec.login or not rec.password:
                    raise ValidationError(
                        _(
                            "The Bank Statement Import API '%(name)s' uses the Bridge API "
                            "and therefore it requires a login and a password.",
                            name=rec.name,
                        )
                    )

    def _bridge_get_token(self, company, result, speedy):
        if not speedy["bridge_company_id2token"].get(company.id):
            token = self._bridge_get_new_token(company, result)
            # at this stage, token can be None
            speedy["bridge_company_id2token"][company.id] = token
        return speedy["bridge_company_id2token"][company.id]

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

    def _bridge_get_new_token(self, company, result):
        assert company
        headers_token = {
            "Bridge-Version": BRIDGE_VERSION,
            "Client-Id": self.login,
            "Client-Secret": self.password,
            "accept": "application/json",
            "content-type": "application/json",
        }
        external_user_identifier = False
        for company_user in self.company_user_ids:
            if company_user.company_id == company:
                external_user_identifier = company_user.identifier
                break
        if not external_user_identifier:
            raise UserError(
                _("Missing Bridge External User Identifier on company '%s'.")
                % company.display_name
            )
        post_json = {"external_user_id": external_user_identifier}
        url = f"{BRIDGE_BASE_URL}/v3/aggregation/authorization/token"
        try:
            token_res = requests.post(
                url, headers=headers_token, json=post_json, timeout=TIMEOUT
            )
        except Exception as e:
            result["logs"].append(
                f"ERROR API call on {url} failed: {e}. "
                f"Could not get a token for company {company.name}."
            )
            return None
        if token_res.status_code != 200:
            result["logs"].append(
                f"ERROR API call on {url} return an HTTP error code "
                f"{token_res.status_code}. Could not get a token for "
                f"company {company.name}."
            )
            return None
        token_dict = token_res.json()
        token = token_dict["access_token"]
        result["logs"].append(
            f"INFO Successful API call on {url} to get a new token "
            f"for company {company.name}"
        )
        logger.debug(
            "New Bridge API session token %s for company %s (user: %s)",
            token,
            company.name,
            external_user_identifier,
        )
        return token

    def _prepare_speedy(self):
        self.ensure_one()
        speedy = super()._prepare_speedy()
        if self.service == "bridge":
            self._check_company_user_identifier()
            speedy["bridge_company_id2token"] = {}
        return speedy

    def _bridge_test_api(self):
        self.ensure_one()
        self._check_company_user_identifier()
        result = {"logs": []}
        company = self.company_id or self.env.company
        self._bridge_get_new_token(company, result)
        for log in result["logs"]:
            if log.startswith("ERROR "):
                raise UserError(
                    _(
                        "Failure in the request to Bridge API. Error: %(err)s",
                        err=log[6:],
                    )
                )

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
                    "identifier": account["id"],
                    "company_id": company.id,
                }
            )
        return res

    @api.model
    def _bridge_get_all_pages(self, api_name, headers, result, params=None):
        url = f"{BRIDGE_BASE_URL}/{BRIDGE_API_VERSION}/{api_name}"
        if params is None:
            params = {}
        if not params.get("limit"):
            params["limit"] = BRIDGE_MAX_PAGE_LIMIT
        try:
            res = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        except Exception as e:
            result["logs"].append(
                f"ERROR API call on {url} with params={params} failed: {e}"
            )
            return None
        if res.status_code != 200:
            result["logs"].append(
                f"ERROR API call on {url} with params={params} returned an "
                f"HTTP error code {res.status_code}."
            )
            return None
        result["logs"].append(f"INFO Successful API call on {url} with params={params}")
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
                result["logs"].append(
                    f"ERROR API call on {url} failed (page {page}): {e}"
                )
                return None
            if res_next_page.status_code != 200:
                result["logs"].append(
                    f"ERROR API call on {url} returned an "
                    f"HTTP error code {res_next_page.status_code} (page {page})."
                )
                return None
            result["logs"].append(f"INFO Successful API call on {url} (page {page})")
            res_next_page_dict = res_next_page.json()
            res_list += res_next_page_dict["resources"]
            next_uri = res_next_page_dict["pagination"].get("next_uri")
        return res_list
