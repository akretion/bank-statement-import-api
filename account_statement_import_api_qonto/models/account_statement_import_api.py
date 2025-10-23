# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

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
            "help": _(
                "Go to the web interface of your Qonto account, go to ... and copy the ..."
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

    def _qonto_test_api(self):
        self.ensure_one()
        speedy = self._prepare_speedy()
        try:
            res = requests.get(
                BASE_URL + "bank_accounts",
                verify=True,
                headers=speedy["headers"],
                timeout=TIMEOUT,
            )
        except Exception as e:
            raise UserError(
                _("Failure in the request to Qonto API. Error: %(err)s", err=e)
            )
        if res.status_code != 200:
            raise UserError(
                _(
                    "The Qonto API returned an HTTP error code (%(status_code)s).",
                    status_code=res.status_code,
                )
            )

    def _update_api_accounts_qonto(self, result, speedy):
        self.ensure_one()
        accounts = self.env["account.journal"]._qonto_get_all_pages(
            "bank_accounts", result, speedy
        )
        res = []
        for account in accounts:
            res.append(
                {
                    "name": account["name"],
                    "account_number": account.get("iban"),
                    "bank_name": account.get("bic"),
                    "identifier": account["id"],
                    "company_id": self.company_id.id,
                }
            )
        return res
