# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .account_journal import BASE_URL, TIMEOUT

logger = logging.getLogger(__name__)


class AccountStatementImportApi(models.Model):
    _inherit = "account.statement.import.api"

    service = fields.Selection(
        selection_add=[
            ("qonto", "Qonto"),
        ],
        ondelete={"qonto": "cascade"},
    )

    @api.constrains("service", "company_id", "login", "password")
    def _check_qonto(self):
        for rec in self:
            if rec.service == "qonto":
                if not rec.company_id:
                    raise ValidationError(
                        _(
                            "The Bank Statement Import API '%(name)s' uses the Qonto API "
                            "and therefore it must be linked to a specific company.",
                            name=rec.name,
                        )
                    )
                if not rec.login or not rec.password:
                    raise ValidationError(
                        _(
                            "The Bank Statement Import API '%(name)s' uses the Qonto API "
                            "and therefore it requires a login and password.",
                            name=rec.name,
                        )
                    )

    @api.model
    def _get_show_backward_days(self, service):
        if service == "qonto":
            return False
        return super()._get_show_backward_days(service)

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
