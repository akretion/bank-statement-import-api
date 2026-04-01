# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

import pytz

from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    powens_preferred_date = fields.Selection(
        [
            ("application_date", "Application Date"),
            ("bdate", "Booking Date"),
            ("rdate", "Transaction Date"),
            ("date", "Date"),
        ],
        default="date",
    )

    def _api_import_powens(self, result, speedy):
        self.ensure_one()
        speedy["powens_preferred_date"] = self.powens_preferred_date
        import_api = self.statement_import_api_id
        company = self.company_id
        headers = import_api._powens_get_headers(company, result, speedy)
        if not headers:
            return  # The error is already in the logs
        # The Powens API reference says:
        # "By default, only active (not deleted) transactions are returned"
        # cf https://docs.powens.com/api-reference/products/data-aggregation/bank-transactions
        if self.statement_import_api_last_success:
            # rewind 1h, just in case
            since_dt = self.statement_import_api_last_success - timedelta(hours=1)
            since_dt_aware = pytz.utc.localize(since_dt)
            since_iso = since_dt_aware.isoformat(timespec="milliseconds")
            if since_iso.endswith("+00:00"):
                since_iso = f"{since_iso[:-6]}Z"
            params = {"last_update": since_iso}
        else:
            params = {
                "filter": "date",  # by default, it filters on "application_date"
                "min_date": self.statement_import_api_start_date,
            }
        user_id = speedy["company_id2user_identifier"][company.id]
        api_name = (
            f"users/{user_id}/accounts/{speedy['account_identifier']}/transactions"
        )
        transactions = import_api._powens_get_all_pages(
            api_name, headers, result, params
        )
        for trans in transactions:
            pivot = self._api_import_powens_prepare_pivot_line(trans, result, speedy)
            if pivot:
                result["lines"].append(pivot)

    def _api_import_powens_prepare_pivot_line(self, trans, result, speedy):
        assert str(trans["id_account"]) == speedy["account_identifier"]
        assert trans["active"]
        date = False
        if speedy["powens_preferred_date"]:
            date = trans.get(speedy["powens_preferred_date"])
        if not date:
            date = trans["date"]
        pivot = {
            "date": date,
            "payment_ref": trans["original_wording"],
            "amount": trans["value"],
            "unique_import_id": str(trans["id"]),
            "transaction_type": trans.get("type"),
            "to_delete": bool(trans["deleted"]),
        }
        return pivot
