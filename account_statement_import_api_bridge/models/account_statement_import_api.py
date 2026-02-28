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
            "login": "config_file",
            "password": "config_file",
            "user_company_required": True,
            "show_backward_days": True,
            "manage_accounts_wizard": True,
            "manage_accounts_wizard_connector_required": True,
            "is_aggregator": True,
            "last_success_source": "last_update_dt",
            # "instructions": _("TODO Write instructions"),
        }
        return service2info

    def _prepare_speedy(self):
        speedy = super()._prepare_speedy()
        speedy["bridge_version"] = BRIDGE_VERSION
        return speedy

    def _bridge_get_token(self, company, result, speedy):
        self.ensure_one()
        if not speedy["company_id2token"].get(company.id):
            token = self._bridge_get_new_token(company, result, speedy)
            # at this stage, token can be None
            speedy["company_id2token"][company.id] = token
        return speedy["company_id2token"][company.id]

    def _bridge_get_headers(self, company, result, speedy):
        self.ensure_one()
        token = self._bridge_get_token(company, result, speedy)
        if not token:
            return None
        headers = {
            "Bridge-Version": speedy["bridge_version"],
            "accept": "application/json",
            "content-type": "application/json",
            "Authorization": "Bearer %s" % token,
            "Client-Id": speedy["login"],
            "Client-Secret": speedy["password"],
        }
        return headers

    def _bridge_get_new_token(self, company, result, speedy):
        self.ensure_one()
        assert company
        ajo = self.env["account.journal"]
        headers_token = {
            "Bridge-Version": speedy["bridge_version"],
            "Client-Id": speedy["login"],
            "Client-Secret": speedy["password"],
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
        token_dict = self._bridge_post(
            "aggregation/authorization/token", headers_token, result, json=post_json
        )
        if not token_dict.get("access_token"):
            ajo._api_import_error_log(
                result,
                f"Could not get a token for company {company.name}.",
            )
            return None
        token = token_dict["access_token"]
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

    def _update_sync_status_bridge(self, result, speedy):
        connector_ident2vals = {}
        for user_company in self.company_user_ids:
            headers = self._bridge_get_headers(user_company.company_id, result, speedy)
            if not headers:
                return connector_ident2vals
            bridge_items = self._bridge_get_all_pages(
                "aggregation/items", headers, result
            )

            for item in bridge_items or []:
                auth_expiry_date = False
                last_sync_datetime = False
                status = "ok"
                messages = []
                if item.get("status", 0) > 0:
                    status = "ko"
                    if item.get("status_code_description"):
                        messages.append(item["status_code_description"])
                    if (
                        item.get("status_code_info")
                        and item["status_code_info"] != "ok"
                    ):
                        messages.append(
                            f"Status Code Type: {item['status_code_info']} "
                            f"(Status Code: {item.get('status')})"
                        )
                if item.get("authentication_expires_at"):
                    auth_expiry_date = self.env[
                        "account.journal"
                    ]._api_import_timestamp_iso8601_to_date(
                        item["authentication_expires_at"], speedy
                    )
                if item.get("last_successful_refresh"):
                    last_sync_datetime = self.env[
                        "account.journal"
                    ]._api_import_timestamp_iso8601_to_datetime(
                        item["last_successful_refresh"], speedy
                    )
                connection_id = str(item["id"])
                connector_ident2vals[connection_id] = {
                    "auth_expiry_date": auth_expiry_date,
                    "last_sync_datetime": last_sync_datetime,
                    "sync_status": status,
                    "sync_status_message": "\n".join(messages) or False,
                }
        return connector_ident2vals

    def _update_api_accounts_bridge(self, company, result, speedy):
        self.ensure_one()
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
        account_ident2vals = {}
        for account in bridge_accounts or []:
            if account["data_access"] == "enabled":
                account_ident2vals[str(account["id"])] = {
                    "name": account["name"],
                    "account_type": account.get("type"),
                    "account_number": account.get("iban"),
                    "bank_name": providers_id2name.get(account.get("provider_id")),
                    "currency_code": account.get("currency_code"),
                    "company_id": company.id,
                    "connector_identifier": str(account["item_id"]),
                }
        return account_ident2vals

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
                result, f"HTTP GET API call on {url} with params={params} failed: {e}"
            )
            return None
        if res.status_code != 200:
            ajo._api_import_error_log(
                result,
                f"HTTP GET API call on {url} with params={params} returned an "
                f"HTTP error code {res.status_code}.",
            )
            return None
        ajo._api_import_info_log(
            result, f"Successful HTTP GET API call on {url} with params={params}"
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

    @api.model
    def _bridge_post(self, api_name, headers, result, json=None):
        ajo = self.env["account.journal"]
        url = f"{BRIDGE_BASE_URL}/{BRIDGE_API_VERSION}/{api_name}"
        try:
            res = requests.post(url, headers=headers, json=json, timeout=TIMEOUT)
        except Exception as e:
            ajo._api_import_error_log(
                result, f"HTTP POST API call on {url} with json={json} failed: {e}"
            )
            return {}
        if res.status_code not in (200, 201):
            try:
                error_msg = res.json()["errors"][0]["message"]
            except Exception:
                error_msg = ""
            ajo._api_import_error_log(
                result,
                f"HTTP POST API call on {url} with json={json} returned an "
                f"HTTP error code {res.status_code} with this error "
                f"message: '{error_msg}'.",
            )
            return {}
        ajo._api_import_info_log(
            result, f"Successful HTTP POST API call on {url} with json={json}"
        )
        res_dict = res.json()
        return res_dict

    def _bridge_add_account_get_url(self, company, result, speedy):
        headers = self._bridge_get_headers(company, result, speedy)
        user_partner = self.env.user.partner_id
        if not user_partner.email:
            raise UserError(
                _("Missing e-mail on partner '%s'.", user_partner.display_name)
            )
        # The parameter user_email is not really important... it is just used to
        # notify the user in case their change the terms of service.
        json = {"user_email": user_partner.email}
        res_json = self._bridge_post(
            "aggregation/connect-sessions", headers, result, json=json
        )
        url = res_json.get("url")
        return url

    def _bridge_manage_accounts_get_url(
        self, connector, company, result, speedy, force_reauthentication=False
    ):
        headers = self._bridge_get_headers(company, result, speedy)
        assert connector
        try:
            item_id = int(connector.identifier)
        except Exception as err:
            raise UserError(
                _(
                    "The identifier of Bank connector '%(connector)s' is "
                    "'%(identifier)s', but it should be an integer. "
                    "Error: %(err)s",
                    connector=connector.display_name,
                    identifier=connector.identifier,
                    err=err,
                )
            ) from err
        json = {
            "item_id": item_id,
            "force_reauthentication": force_reauthentication,
        }
        res_json = self._bridge_post(
            "aggregation/connect-sessions", headers, result, json=json
        )
        url = res_json.get("url")
        return url

    def _bridge_renew_auth_get_url(self, connector, company, result, speedy):
        return self._bridge_manage_accounts_get_url(
            connector, company, result, speedy, force_reauthentication=True
        )
