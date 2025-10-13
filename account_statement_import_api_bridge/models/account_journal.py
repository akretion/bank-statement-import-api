# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

import pytz
import requests

from odoo import Command, _, fields, models
from odoo.exceptions import UserError

BRIDGE_BASE_URL = "https://api.bridgeapi.io"
BRIDGE_MAX_PAGE_LIMIT = 500
TIMEOUT = 20


class AccountJournal(models.Model):
    _inherit = "account.journal"

    bridge_account_identifier = fields.Integer()  # readonly=True
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
        speedy["bridge_preferred_date"] = self.bridge_preferred_date
        import_api = self.statement_import_api_id
        headers = import_api._bridge_get_headers(self.company_id, result, speedy)
        # I would like to filter-out future lines, but it not possible in params
        params = {
            "account_id": self.bridge_account_identifier,
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

        url = f"{BRIDGE_BASE_URL}/v3/aggregation/transactions"
        transactions = self._bridge_get_all_pages(url, headers, result, params)
        if transactions:
            for trans in transactions:
                pivot = self._api_import_bridge_prepare_pivot_line(
                    trans, result, speedy
                )
                if pivot:
                    result["lines"].append(pivot)

    def _api_import_bridge_prepare_pivot_line(self, trans, result, speedy):
        assert trans["account_id"] == self.bridge_account_identifier
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

    def bridge_set_account_identifier(self):
        self.ensure_one()
        assert not self.bridge_account_identifier
        result = {"logs": []}
        import_api = self.statement_import_api_id
        speedy = import_api._prepare_speedy()
        headers = import_api._bridge_get_headers(self.company_id, result, speedy)
        url = f"{BRIDGE_BASE_URL}/v3/providers"
        providers = self._bridge_get_all_pages(url, headers, result)
        if providers is None:
            raise UserError(result["logs"][-1])
        providers_id2name = {}
        for provider in providers:
            providers_id2name[provider["id"]] = provider["name"]

        url = f"{BRIDGE_BASE_URL}/v3/aggregation/accounts"
        bridge_accounts = self._bridge_get_all_pages(url, headers, result)
        if bridge_accounts is None:
            raise UserError(result["logs"][-1])
        existing_identifiers_read = self.search_read(
            [
                ("company_id", "=", self.company_id.id),
                ("bridge_account_identifier", "!=", False),
            ],
            ["bridge_account_identifier"],
        )
        existing_identifiers = [
            x["bridge_account_identifier"] for x in existing_identifiers_read
        ]
        bridge_account_identifier = False
        iban_acc_number = False
        if self.bank_account_id and self.bank_account_id.acc_type == "iban":
            iban_acc_number = self.bank_account_id.sanitized_acc_number
        bridge_options = []
        for bridge_account in bridge_accounts:
            if bridge_account["id"] not in existing_identifiers:
                if iban_acc_number and bridge_account.get("iban") == iban_acc_number:
                    bridge_account_identifier = bridge_account["id"]
                    break
                bridge_provider_name = False
                if (
                    bridge_account.get("provider_id")
                    and bridge_account["provider_id"] in providers_id2name
                ):
                    bridge_provider_name = providers_id2name[
                        bridge_account["provider_id"]
                    ]
                bridge_options.append(
                    {
                        "name": bridge_account["name"],
                        "account_type": bridge_account.get("type"),
                        "iban": bridge_account.get("iban"),
                        "bridge_provider_name": bridge_provider_name,
                        "bridge_identifier": bridge_account["id"],
                    }
                )

        if bridge_account_identifier:
            self.write({"bridge_account_identifier": bridge_account_identifier})
        else:
            wiz = self.env["bridge.match.account"].create(
                {
                    "journal_id": self.id,
                    "option_ids": [Command.create(x) for x in bridge_options],
                }
            )
            action = {
                "type": "ir.actions.act_window",
                "res_model": "bridge.match.account",
                "name": _("Set Bridge Account Identifier"),
                "view_mode": "form",
                "res_id": wiz.id,
                "target": "new",
            }
            return action

    def _bridge_get_all_pages(self, url, headers, result, params=None):
        if params is None:
            params = {}
        if not params.get("limit"):
            params["limit"] = BRIDGE_MAX_PAGE_LIMIT
        try:
            res = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        except Exception as e:
            result["logs"].append(
                f"ERROR API call on {url} with params={params} failed: {e}"
            )
            return None
        if res.status_code != 200:
            result["logs"].append(
                f"ERROR API call on {url} with params={params} returned an "
                f"HTTP error code {res.status_code}."
            )
            return None
        result["logs"].append(f"INFO Successful API call on {url} with params={params}")
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
                result["logs"].append(
                    f"ERROR API call on {url} failed (page {page}): {e}"
                )
                return None
            if res_next_page.status_code != 200:
                result["logs"].append(
                    f"ERROR API call on {url} returned an "
                    f"HTTP error code {res_next_page.status_code} (page {page})."
                )
                return None
            result["logs"].append(f"INFO Successful API call on {url} (page {page})")
            res_next_page_dict = res_next_page.json()
            res_list += res_next_page_dict["resources"]
            next_uri = res_next_page_dict["pagination"].get("next_uri")
        return res_list
