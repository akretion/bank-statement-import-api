# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import requests

from odoo import _, api, fields, models, tools
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
    bridge_external_user_identifier = fields.Char(
        string="Bridge API External User Identifier", readonly=True, copy=False
    )

    _sql_constraints = [
        (
            "bridge_external_user_identifier_unique",
            "unique(bridge_external_user_identifier)",
            "This Bridge API external identifier is already used on other "
            "bank statement import API.",
        ),
    ]

    def init(self):
        self._cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
            single_bridge_statement_import_api_per_company
            ON account_statement_import_api
            (company_id) WHERE service = 'bridge'
            """
        )

    @api.model
    def _get_service_info(self):
        service2info = super()._get_service_info()
        service2info["bridge"] = {
            "name": "BridgeAPI.io",
            "login": "config_file",
            "password": "config_file",
            "is_aggregator": True,
            "manage_accounts_wizard_connector_required": True,
            "last_success_source": "last_update_dt",
        }
        return service2info

    def _prepare_speedy(self):
        speedy = super()._prepare_speedy()
        if self.service == "bridge":
            url = tools.config.get("account_statement_import_api_bridge_url")
            if url:
                url = url.strip()
                if url.endswith("/"):
                    url = url[:-1]
            else:
                url = BRIDGE_BASE_URL
            headers_no_token = {
                "Bridge-Version": BRIDGE_VERSION,
                "accept": "application/json",
                "content-type": "application/json",
                "Client-Id": speedy["login"],
                "Client-Secret": speedy["password"],
            }
            speedy.update(
                {
                    "bridge_base_url": url,
                    "bridge_max_page_limit": BRIDGE_MAX_PAGE_LIMIT,
                    "bridge_headers_no_token": headers_no_token,
                }
            )
        return speedy

    def _bridge_get_token(self, result, speedy):
        self.ensure_one()
        if not speedy.get("bridge_token"):
            token = self._bridge_get_new_token(result, speedy)
            # at this stage, token can be None
            speedy["bridge_token"] = token
        return speedy["bridge_token"]

    def _bridge_get_headers(self, result, speedy):
        self.ensure_one()
        token = self._bridge_get_token(result, speedy)
        if not token:
            return None
        headers = speedy["bridge_headers_no_token"]
        headers["Authorization"] = f"Bearer {token}"
        return headers

    def _bridge_get_new_token(self, result, speedy):
        self.ensure_one()
        headers_token = speedy["bridge_headers_no_token"]
        user_uuid = self.sudo().user_identifier
        post_json = {"user_uuid": user_uuid}
        token_dict = self._bridge_post(
            "aggregation/authorization/token",
            headers_token,
            result,
            speedy,
            json=post_json,
        )
        if not token_dict.get("access_token"):
            speedy["log_obj"]._error_log(result, "Could not get a token.")
            return None
        token = token_dict["access_token"]
        logger.debug(
            "New Bridge API session token %s (user UUID: %s)",
            token,
            user_uuid,
        )
        return token

    def _bridge_test_api(self, result, speedy):
        self.ensure_one()
        self._bridge_get_new_token(result, speedy)

    def _bridge_update_sync_status(self, result, speedy):
        self.ensure_one()
        connector_ident2vals = {}
        headers = self._bridge_get_headers(result, speedy)
        if not headers:
            return connector_ident2vals
        logger.info(
            "Get BridgeAPI connector status for Statement import API %s company %s",
            self.display_name,
            self.company_id.display_name,
        )
        bridge_items = self._bridge_get_all_pages(
            "aggregation/items", headers, result, speedy
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
                if item.get("status_code_info") and item["status_code_info"] != "ok":
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

    def _bridge_get_api_accounts(self, flavor, result, speedy):
        self.ensure_one()
        assert flavor in ("balance", "properties")
        headers = self._bridge_get_headers(result, speedy)
        if not headers:
            return None
        bridge_accounts = self._bridge_get_all_pages(
            "aggregation/accounts", headers, result, speedy
        )
        account_ident2vals = {}
        provider_ids = set()
        for account in bridge_accounts or []:
            if account["data_access"] == "enabled":
                account_ident = str(account["id"])
                bal = None
                if "balance" in account:
                    bal = account["balance"]
                debug_msg = []
                if "accounting_balance" in account:
                    debug_msg.append(
                        f"accounting_balance={account['accounting_balance']}"
                    )
                if "instant_balance" in account:
                    debug_msg.append(f"instant_balance={account['instant_balance']}")
                if debug_msg:
                    msg = (
                        f"Other balances for account identifier {account_ident}: "
                        f"{' '.join(debug_msg)}"
                    )
                    speedy["log_obj"]._debug_log(result, msg)
                account_ident2vals[account_ident] = {
                    "name": account["name"],
                    "account_type": account.get("type"),
                    "account_number": account.get("iban"),
                    "currency_code": account.get("currency_code"),
                    "connector_identifier": str(account["item_id"]),
                    "provider_id": account.get("provider_id"),  # temp key
                    "balance": bal,
                }
                if flavor == "properties" and account.get("provider_id"):
                    provider_ids.add(account["provider_id"])
        if flavor == "properties":
            providers_id2name = {}
            for provider_id in provider_ids:
                provider_dict = self._bridge_get(
                    f"providers/{provider_id}", headers, result, speedy
                )
                if provider_dict:
                    providers_id2name[provider_id] = provider_dict.get("name")
            for vals in account_ident2vals.values():
                if vals["provider_id"] and vals["provider_id"] in providers_id2name:
                    provider_id = vals.pop("provider_id")
                    vals["bank_name"] = providers_id2name[provider_id]
        return account_ident2vals

    @api.model
    def _bridge_get(self, api_name, headers, result, speedy, params=None):
        url = f"{speedy['bridge_base_url']}/{BRIDGE_API_VERSION}/{api_name}"
        try:
            res = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        except Exception as e:
            speedy["log_obj"]._error_log(
                result, f"HTTP GET API call on {url} with params={params} failed: {e}"
            )
            return None
        logger.debug("Headers of the answer from Bridge: %s", res.headers)
        if res.status_code != 200:
            speedy["log_obj"]._error_log(
                result,
                f"HTTP GET API call on {url} with params={params} returned an "
                f"HTTP error code {res.status_code}.",
            )
            return None
        speedy["log_obj"]._info_log(
            result, f"Successful HTTP GET API call on {url} with params={params}"
        )
        res_dict = res.json()
        return res_dict

    @api.model
    def _bridge_get_all_pages(self, api_name, headers, result, speedy, params=None):
        if params is None:
            params = {}
        if not params.get("limit"):
            params["limit"] = speedy["bridge_max_page_limit"]
        res_dict = self._bridge_get(api_name, headers, result, speedy, params=params)
        if res_dict is None:
            return None
        res_list = res_dict["resources"]
        next_uri = res_dict["pagination"].get("next_uri")
        page = 1
        while next_uri:
            page += 1
            url = f"{speedy['bridge_base_url']}{next_uri}"
            try:
                res_next_page = requests.get(url, headers=headers, timeout=TIMEOUT)
            except Exception as e:
                speedy["log_obj"]._error_log(
                    result, f"API call on {url} failed (page {page}): {e}"
                )
                return None
            if res_next_page.status_code != 200:
                speedy["log_obj"]._error_log(
                    result,
                    f"API call on {url} returned an "
                    f"HTTP error code {res_next_page.status_code} (page {page}).",
                )
                return None
            speedy["log_obj"]._info_log(
                result, f"Successful API call on {url} (page {page})"
            )
            res_next_page_dict = res_next_page.json()
            res_list += res_next_page_dict["resources"]
            next_uri = res_next_page_dict["pagination"].get("next_uri")
        return res_list

    @api.model
    def _bridge_post(self, api_name, headers, result, speedy, json=None):
        url = f"{speedy['bridge_base_url']}/{BRIDGE_API_VERSION}/{api_name}"
        try:
            res = requests.post(url, headers=headers, json=json, timeout=TIMEOUT)
        except Exception as e:
            speedy["log_obj"]._error_log(
                result, f"HTTP POST API call on {url} with json={json} failed: {e}"
            )
            return {}
        logger.debug("Headers of the answer from Bridge: %s", res.headers)
        if res.status_code not in (200, 201):
            try:
                error_msg = res.json()["errors"][0]["message"]
            except Exception:
                error_msg = res.text
            speedy["log_obj"]._error_log(
                result,
                f"HTTP POST API call on {url} with json={json} returned an "
                f"HTTP error code {res.status_code} with this error "
                f"message: '{error_msg}'.",
            )
            return {}
        speedy["log_obj"]._info_log(
            result, f"Successful HTTP POST API call on {url} with json={json}"
        )
        res_dict = res.json()
        return res_dict

    @api.model
    def _bridge_del(self, api_name, headers, result, speedy):
        url = f"{speedy['bridge_base_url']}/{BRIDGE_API_VERSION}/{api_name}"
        try:
            res = requests.delete(url, headers=headers, timeout=TIMEOUT)
        except Exception as e:
            speedy["log_obj"]._error_log(
                result, f"HTTP DELETE API call on {url} failed: {e}"
            )
            return False
        logger.debug("Headers of the answer from Bridge: %s", res.headers)
        if res.status_code != 204:
            try:
                error_msg = res.json()["errors"][0]["message"]
            except Exception:
                error_msg = res.text
            speedy["log_obj"]._error_log(
                result,
                f"HTTP DELETE API call on {url} returned an "
                f"HTTP error code {res.status_code} with this error "
                f"message: '{error_msg}'.",
            )
            return False
        speedy["log_obj"]._info_log(result, f"Successful HTTP DELETE API call on {url}")
        return True

    def _bridge_add_account_get_url(self, result, speedy):
        self.ensure_one()
        headers = self._bridge_get_headers(result, speedy)
        user_partner = self.env.user.partner_id
        if not user_partner.email:
            raise UserError(
                _("Missing e-mail on partner '%s'.", user_partner.display_name)
            )
        # The parameter user_email is not really important... it is just used to
        # notify the user in case their change the terms of service.
        json = {"user_email": user_partner.email}
        res_json = self._bridge_post(
            "aggregation/connect-sessions", headers, result, speedy, json=json
        )
        url = res_json.get("url")
        return url

    def _bridge_manage_accounts_get_url(
        self, connector, result, speedy, force_reauthentication=False
    ):
        self.ensure_one()
        headers = self._bridge_get_headers(result, speedy)
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
            "aggregation/connect-sessions", headers, result, speedy, json=json
        )
        url = res_json.get("url")
        return url

    def _bridge_renew_auth_get_url(self, connector, result, speedy):
        return self._bridge_manage_accounts_get_url(
            connector, result, speedy, force_reauthentication=True
        )

    def _bridge_delete_connector(self, connector, result, speedy):
        self.ensure_one()
        url_path = f"aggregation/items/{connector.identifier}"
        headers = self._bridge_get_headers(result, speedy)
        res = self._bridge_del(url_path, headers, result, speedy)
        return res

    def _bridge_delete_user(self, result, speedy):
        self.ensure_one()
        url_path = f"aggregation/users/{self.user_identifier}"
        res = self._bridge_del(
            url_path, speedy["bridge_headers_no_token"], result, speedy
        )
        return res

    def _prepare_delete_user(self):
        vals = super()._prepare_delete_user()
        if self.service == "bridge":
            vals["bridge_external_user_identifier"] = False
        return vals
