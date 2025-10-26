# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import urllib.parse
from socket import getaddrinfo

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

POWENS_API_VERSION = "2.0"
POWENS_MAX_PAGE_LIMIT = 1000
TIMEOUT = 20
# Info source: https://docs.powens.com/api-reference/overview/webview
POWENS_WEBVIEW_LANGS = ("en", "fr", "de", "nl", "pt", "it", "es")
POWENS_WEBVIEW_BASE_URL = "https://webview.powens.com"

logger = logging.getLogger(__name__)


class AccountStatementImportApi(models.Model):
    _inherit = "account.statement.import.api"

    service = fields.Selection(ondelete={"powens": "cascade"})
    powens_hostname = fields.Char()
    powens_redirect_url = fields.Char(string="Powens Redirect URL")

    @api.constrains("service", "powens_hostname", "powens_redirect_url")
    def _check_powens_config(self):
        for rec in self:
            if rec.service == "powens":
                if not rec.powens_hostname or (
                    rec.powens_hostname and not rec.powens_hostname.strip()
                ):
                    raise ValidationError(
                        _("Missing Powens Hostname on Bank Statement Import API '%s'.")
                        % rec.display_name
                    )
                if not rec.powens_redirect_url:
                    raise ValidationError(
                        _(
                            "Missing Powens Redirect URL on Bank Statement Import API '%s'."
                        )
                        % rec.display_name
                    )

    @api.model
    def _get_service_info(self):
        service2info = super()._get_service_info()
        service2info["powens"] = {
            "name": "Powens",
            "company_required": False,
            "login_required": True,
            "password_required": True,
            "user_company_required": True,
            "show_backward_days": True,
            # "instructions": _("TODO"),
        }
        return service2info

    def _prepare_speedy(self):
        speedy = super()._prepare_speedy()
        if speedy["service"] == "powens":
            for company_user in self.sudo().company_user_ids:
                if company_user.powens_token:
                    company_id = company_user.company_id.id
                    speedy["company_id2token"][company_id] = company_user.powens_token
        return speedy

    def _powens_get_headers(self, company, result, speedy):
        token = speedy["company_id2token"].get(company.id)
        if not token:
            raise UserError(
                _(
                    "On bank statement import API '%(import_api)s', "
                    "missing user identifier with Powens token "
                    "on company '%(company)s'.",
                    import_api=self.display_name,
                    company=company.display_name,
                )
            )
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "Authorization": "Bearer %s" % token,
        }
        return headers

    def _powens_check_hostname(self, result):
        assert self.powens_hostname
        hostname = self.powens_hostname.strip()
        assert hostname
        # check DNS
        try:
            getaddrinfo(hostname, None)
            logger.info("Powens DNS %s is valid", hostname)
        except Exception as e:
            self.env["account.journal"]._api_import_error_log(
                result,
                _(
                    "Powens hostname '%(hostname)s' cannot be resolved. "
                    "The hostname is wrong or the Internet connection of "
                    "the Odoo server is down. Error: %(err)s.",
                    hostname=hostname,
                    err=e,
                ),
            )

    def _powens_test_api(self, result, speedy):
        self.ensure_one()
        self._powens_check_hostname(result)
        company = self.company_id or self.env.company
        headers = self._powens_get_headers(company, result, speedy)
        self._powens_get_all_pages("account_types", headers, result)

    def _update_api_accounts_powens(self, result, speedy):
        self.ensure_one()
        company = self.company_id or self.env.company
        headers = self._powens_get_headers(company, result, speedy)
        if not headers:
            return None
        user_id = speedy["company_id2user_identifier"][company.id]
        api_name = f"users/{user_id}/accounts"

        powens_accounts = self._powens_get_all_pages(api_name, headers, result)
        res = []
        id_connection2expiry = {}
        for account in powens_accounts or []:
            # pprint(account)
            res.append(
                {
                    "name": account["name"],
                    "account_type": account.get("type"),
                    "account_number": account.get("iban") or account.get("number"),
                    "bank_name": account.get("bic"),
                    "currency_code": account.get("currency")
                    and account["currency"].get("id"),
                    "identifier": account["id"],
                    "company_id": company.id,
                    "powens_id_connection": account["id_connection"],
                }
            )
            id_connection2expiry[account["id_connection"]] = None
        for id_connection in id_connection2expiry.keys():
            api_name = f"users/{user_id}/connections/{id_connection}/sources"
            sources = self._powens_get(api_name, headers, result)
            for source in sources:
                if source.get("id_connection") == id_connection and source.get(
                    "access_expire"
                ):
                    id_connection2expiry[id_connection] = source["access_expire"][:10]
        for vals in res:
            id_connection = vals.pop("powens_id_connection")
            if id_connection2expiry.get(id_connection):
                vals["auth_expiry_date"] = id_connection2expiry[id_connection]
        return res

    @api.model
    def _powens_get_all_pages(self, api_name, headers, result, params=None):
        ajo = self.env["account.journal"]
        url = f"https://{self.powens_hostname}/{POWENS_API_VERSION}/{api_name}"
        if params is None:
            params = {}
        if not params.get("limit"):
            params["limit"] = POWENS_MAX_PAGE_LIMIT
        try:
            res = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
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
        ajo._api_import_info_log(
            result, f"Successful API call on {url} with params={params}"
        )
        res_dict = res.json()
        answer_key = api_name.split("/")[-1].replace("_", "")
        res_list = res_dict[answer_key]
        next_url = (
            res_dict.get("_links")
            and res_dict["_links"].get("next")
            and res_dict["_links"]["next"].get("href")
        )
        page = 1
        while next_url:
            page += 1
            try:
                res_next_page = requests.get(next_url, headers=headers, timeout=TIMEOUT)
            except Exception as e:
                ajo._api_import_error_log(
                    result, f"API call on {next_url} failed (page {page}): {e}"
                )
                return []
            if res_next_page.status_code != 200:
                ajo._api_import_error_log(
                    result,
                    f"API call on {next_url} returned an "
                    f"HTTP error code {res_next_page.status_code} (page {page}).",
                )
                return []
            ajo._api_import_info_log(
                result, f"Successful API call on {url} (page {page})"
            )
            res_next_page_dict = res_next_page.json()
            res_list += res_next_page_dict[answer_key]
            next_url = (
                res_next_page_dict.get("_links")
                and res_next_page_dict["_links"].get("next")
                and res_next_page_dict["_links"]["next"].get("href")
            )
        return res_list

    @api.model
    def _powens_get(self, api_name, headers, result, params=None):
        ajo = self.env["account.journal"]
        url = f"https://{self.powens_hostname}/{POWENS_API_VERSION}/{api_name}"
        try:
            res = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
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
        ajo._api_import_info_log(
            result, f"Successful API call on {url} with params={params}"
        )
        res_dict = res.json()
        answer_key = api_name.split("/")[-1].replace("_", "")
        if answer_key in res_dict:
            return res_dict[answer_key]
        return res_dict

    def _powens_get_add_account_url(self, company, result, speedy):
        headers = self._powens_get_headers(company, result, speedy)
        params = {"type": "singleAccess"}
        code = self._powens_get("auth/token/code", headers, result, params=params)
        webview_url_params = {
            "code": code,
            "redirect_uri": self.powens_redirect_url,
            "client_id": self.login,
            "domain": self.powens_hostname,
        }
        if self.env.user.lang and self.env.user.lang.startswith(POWENS_WEBVIEW_LANGS):
            webview_lang = self.env.user.lang[:2]
        else:
            webview_lang = "en"
        webview_url_params_encoded = urllib.parse.urlencode(webview_url_params)
        webview_url = f"{POWENS_WEBVIEW_BASE_URL}/{webview_lang}/connect?{webview_url_params_encoded}"
        return webview_url
