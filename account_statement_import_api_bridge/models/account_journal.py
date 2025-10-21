# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

import pytz

from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    bridge_preferred_date = fields.Selection(
        [
            ("booking_date", "Booking Date"),
            ("value_date", "Value Date"),
            ("transaction_date", "Transaction Date"),
            ("date", "date"),
        ],
        default="booking_date",
    )

    def _api_import_bridge(self, result, speedy):
        self.ensure_one()
        if not self.statement_import_api_account_identifier:
            result["logs"].append("ERROR Bridge Account Identifier is not set")
            return
        speedy["bridge_preferred_date"] = self.bridge_preferred_date
        import_api = self.statement_import_api_id
        headers = import_api._bridge_get_headers(self.company_id, result, speedy)
        # I would like to filter-out future lines, but it not possible in params
        params = {
            "account_id": self.statement_import_api_account_identifier,
        }
        if self.statement_import_api_last_success:
            # rewind 1h, just in case
            since_dt = self.statement_import_api_last_success - timedelta(hours=1)
            since_dt_aware = pytz.utc.localize(since_dt)
            since_iso = since_dt_aware.isoformat(timespec="milliseconds")
            if since_iso.endswith("+00:00"):
                since_iso = f"{since_iso[:-6]}Z"
            params["since"] = since_iso
        else:
            params["min_date"] = self.statement_import_api_start_date - timedelta(
                import_api.backward_days
            )

        transactions = import_api._bridge_get_all_pages(
            "aggregation/transactions", headers, result, params
        )
        if transactions:
            for trans in transactions:
                pivot = self._api_import_bridge_prepare_pivot_line(
                    trans, result, speedy
                )
                if pivot:
                    result["lines"].append(pivot)

    def _api_import_bridge_prepare_pivot_line(self, trans, result, speedy):
        print(trans)
        assert str(trans["account_id"]) == self.statement_import_api_account_identifier
        if speedy["bridge_preferred_date"]:
            date = trans.get(speedy["bridge_preferred_date"])
        else:
            date = trans.get("booking_date")
        # 'date' is the only field that is always set
        if not date:
            date = trans["date"]
        pivot = {
            "currency_code": trans["currency_code"],
            "date": date,
            "payment_ref": trans["provider_description"],
            "amount": trans["amount"],
            "unique_import_id": str(trans["id"]),
        }
        if trans["future"]:
            result["logs"].append(
                f"INFO Skipped transaction dated {pivot['date']} "
                f"amount {pivot['amount']} label '{pivot['payment_ref']}' "
                f"which has future flag"
            )
            return False
        if trans["deleted"]:
            result["logs"].append(
                f"WARN Skipped transaction dated {pivot['date']} "
                f"amount {pivot['amount']} label '{pivot['payment_ref']}' "
                f"which has the deleted flag. It should never happen."
            )
            return False
        return pivot
