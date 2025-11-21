# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import datetime, timedelta

import pytz

from odoo import models

logger = logging.getLogger(__name__)

BASE_URL = "https://thirdparty.qonto.com/v2/"
TIMEOUT = 20


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _api_import_qonto(self, result, speedy):
        self.ensure_one()
        lines = []
        if self.bank_account_id.acc_type != "iban":
            self._api_import_error_log(
                result,
                f"Bank account {self.bank_account_id.acc_number} is not "
                f"an IBAN (account type is '{self.bank_account_id.acc_type}').",
            )
            return

        if self.statement_import_api_last_success:
            # rewind 1h, just in case
            from_dt = self.statement_import_api_last_success - timedelta(hours=1)
            from_dt_aware = pytz.utc.localize(from_dt)
        else:
            from_dt = datetime.combine(
                self.statement_import_api_start_date, datetime.min.time()
            )
            from_dt_aware = speedy["tz"].localize(from_dt)
        params = {
            "status": ["completed"],
            "updated_at_from": from_dt_aware.isoformat(),
            "includes[]": ["vat_details", "attachments"],
        }
        # TODO: when transition is finished, we should always use params['bank_account_id']
        if self.statement_import_api_account_identifier:
            params["bank_account_id"] = self.statement_import_api_account_identifier
        else:
            params["iban"] = self.bank_account_id.sanitized_acc_number
        transactions = self.statement_import_api_id._qonto_get_all_pages(
            "transactions", result, speedy, params=params
        )
        for trans in transactions:
            pivot = self._api_import_qonto_prepare_pivot_line(trans, result, speedy)
            if pivot:
                lines.append(pivot)
        result["lines"] = lines

    def _api_import_qonto_prepare_pivot_line(self, trans, result, speedy):
        sign = trans["side"] == "debit" and -1 or 1
        vat_rate = False
        vat_details_list = trans["vat_details"]["items"]
        if vat_details_list and trans["vat_amount"]:
            # I take the rate of the line with the biggest untaxed base
            base2rate = {
                x["amount_excluding_vat_cents"]: x["rate"]
                for x in vat_details_list
                if x["amount_excluding_vat_cents"]
            }
            base2rate_list_sorted = sorted(base2rate.items(), key=lambda x: x[0])
            vat_rate = base2rate_list_sorted[-1][1]
        attachments = []
        for attach in trans["attachments"]:
            attachments.append(
                {
                    "url": attach["url"],
                    "identifier": attach["id"],
                    "filename": attach["file_name"],
                }
            )
        pivot = {
            "date": self._api_import_timestamp_iso8601_to_date(
                trans["settled_at"], speedy
            ),
            "amount": trans["amount"]
            * sign,  # 'amount' is in the currency of the bank account
            "currency_code": trans["currency"],  # currency of the bank account
            "foreign_currency_code": trans["local_currency"],
            "foreign_currency_amount": trans["local_amount"] * sign,
            "payment_ref": trans["label"],
            "unique_import_id": trans["transaction_id"],
            "attachments": attachments,
            "in_invoice_vat_amount": trans["vat_amount"],
            "in_invoice_vat_rate": vat_rate,
            "in_invoice_expense_description": trans["note"],
            "in_invoice_card_code": trans["card_last_digits"],
            "in_invoice_expense_categ_code": trans["category"],
            "in_invoice_force_invoice_date": self._api_import_timestamp_iso8601_to_date(
                trans["emitted_at"][:10], speedy
            ),
        }
        if trans["reference"]:
            pivot["payment_ref"] = " ".join([pivot["payment_ref"], trans["reference"]])
        if trans["operation_type"] == "qonto_fee":
            pivot["in_invoice_expense_categ_code"] = "qonto_fee"
        return pivot
