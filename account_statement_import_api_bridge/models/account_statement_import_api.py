# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .account_journal import BRIDGE_BASE_URL, TIMEOUT

BRIDGE_VERSION = "2025-01-15"

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
        if not speedy["bridge_user2token"].get(company.bridge_external_user_identifier):
            token = self._bridge_get_new_token(company, result)
            speedy["bridge_user2token"][company.bridge_external_user_identifier] = token
        return speedy["bridge_user2token"][company.bridge_external_user_identifier]

    def _bridge_get_headers(self, company, result, speedy):
        token = self._bridge_get_token(company, result, speedy)
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
        if not company.bridge_external_user_identifier:
            raise UserError(
                _("Missing Bridge External User Identifier on company '%s'.")
                % company.display_name
            )
        post_json = {"external_user_id": company.bridge_external_user_identifier}
        url = f"{BRIDGE_BASE_URL}/v3/aggregation/authorization/token"
        try:
            token_res = requests.post(
                url, headers=headers_token, json=post_json, timeout=TIMEOUT
            )
        except Exception as e:
            result["logs"].append(f"ERROR API call on {url} failed: {e}")
            return
        if token_res.status_code != 200:
            result["logs"].append(
                f"ERROR API call on {url} return an HTTP error code {token_res.status_code}"
            )
            return
        token_dict = token_res.json()
        token = token_dict["access_token"]
        logger.debug(
            "New Bridge API session token: %s (user: %s)",
            token,
            company.bridge_external_user_identifier,
        )
        return token

    def _check_bridge_external_user_identifier(self):
        self.ensure_one()
        companies = self.env["res.company"]
        for journal in self.journal_ids:
            companies |= journal.company_id
        companies_missing_external_user_identifier = companies.filtered(
            lambda x: not x.bridge_external_user_identifier
        )
        if companies_missing_external_user_identifier:
            raise UserError(
                _(
                    "Missing Bridge External User Identifier on the following companies:\n%s."
                )
                % "\n".join(
                    [
                        f"- {c.display_name}"
                        for c in companies_missing_external_user_identifier
                    ]
                )
            )

    def _prepare_speedy(self):
        self.ensure_one()
        speedy = super()._prepare_speedy()
        if self.service == "bridge":
            self._check_bridge_external_user_identifier()
            speedy["bridge_user2token"] = {}
        return speedy

    def _bridge_test_api(self):
        self.ensure_one()
        self._check_bridge_external_user_identifier()
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
