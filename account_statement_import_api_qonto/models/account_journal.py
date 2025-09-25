# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import datetime, timedelta

import pytz
import requests

from odoo import models

logger = logging.getLogger(__name__)

BASE_URL = "https://thirdparty.qonto.com/v2/"
TIMEOUT = 30


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _api_import_qonto(self, result, speedy):
        self.ensure_one()
        lines = []
        if self.bank_account_id.acc_type != "iban":
            # We don't translate logs... would be too much translation work for no big add value
            result["logs"].append(
                f"ERROR Bank account {self.bank_account_id.acc_number} is not "
                f"an IBAN (account type is '{self.bank_account_id.acc_type}')."
            )
            return

        page = total_pages = 1
        if self.statement_import_api_last_success:
            from_dt = self.statement_import_api_last_success
            # rewind 1h, just in case
            from_dt -= timedelta(hours=1)
            from_dt_aware = pytz.utc.localize(from_dt)
        else:
            from_dt = datetime.combine(
                self.statement_import_api_start_date, datetime.min.time()
            )
            from_dt_aware = speedy["tz"].localize(from_dt)
        params = {
            "iban": self.bank_account_id.sanitized_acc_number,
            "status": ["completed"],
            "updated_at_from": from_dt_aware.isoformat(),
            "page": page,
        }
        url = BASE_URL + "transactions"
        while page <= total_pages:
            try:
                res = requests.get(
                    url,
                    verify=True,
                    headers=speedy["headers"],
                    params=params,
                    timeout=TIMEOUT,
                )
            except Exception as e:
                result["logs"].append(
                    f"ERROR API call on {url} with params={params} failed: {e}"
                )
                return
            if res.status_code != 200:
                result["logs"].append(
                    f"ERROR API call on {url} with params={params} returned an "
                    f"HTTP error code {res.status_code}."
                )
                return
            result["logs"].append(
                f"INFO Successful API call on {url} with params={params}"
            )
            qvals = res.json()
            total_pages = qvals["meta"]["total_pages"]
            for trans in qvals["transactions"]:
                sign = trans["side"] == "debit" and -1 or 1
                pivot = {
                    "date": self._api_import_timestamp_iso8601_to_date(
                        trans["settled_at"], speedy
                    ),
                    "amount": trans["amount"]
                    * sign,  # 'amount' is in the currency of the bank account
                    "currency_code": trans["currency"],  # currency of the bank account
                    "payment_ref": trans["label"],
                    "unique_import_id": trans["transaction_id"],
                    "attachment_identifiers": trans["attachment_ids"],
                    "in_invoice_vat_amount": trans["vat_amount"],
                    "in_invoice_vat_rate": trans["vat_rate"],
                    "in_invoice_expense_description": trans["note"],
                    "in_invoice_card_code": trans["card_last_digits"],
                    "in_invoice_expense_categ_code": trans["category"],
                    "in_invoice_force_invoice_date": self._api_import_timestamp_iso8601_to_date(
                        trans["emitted_at"][:10], speedy
                    ),
                }
                if trans["reference"]:
                    pivot["payment_ref"] = " ".join(
                        [pivot["payment_ref"], trans["reference"]]
                    )
                lines.append(pivot)
            page += 1
        result["lines"] = lines

    def _api_import_attachment_qonto(self, qonto_attach_identifier, result, speedy):
        url = f"{BASE_URL}/attachments/{qonto_attach_identifier}"
        try:
            res1 = requests.get(
                url, verify=True, headers=speedy["headers"], timeout=TIMEOUT
            )
        except Exception as e:
            result["logs"].append(f"ERROR API call on {url} failed: {e}")
            return None
        if res1.status_code != 200:
            # let's see error_logs
            result["logs"].append(
                f"ERROR API call on {url} returned an HTTP error code {res1.status_code}."
            )
            return None
        res1_dict = res1.json()
        filename = res1_dict["attachment"]["file_name"]
        url_dl = res1_dict["attachment"]["url"]
        if url_dl and filename:
            try:
                res2 = requests.get(url_dl, verify=True, timeout=TIMEOUT)
            except Exception as e:
                result["logs"].append(f"ERROR API call on {url_dl} failed: {e}")
                return None
            if res2.status_code != 200:
                # let's see error_logs
                result["logs"].append(
                    f"ERROR API call on {url_dl} returned an HTTP error code "
                    f"{res2.status_code}."
                )
                return None
            if res2.content:
                return (filename, res2.content)
        return None
