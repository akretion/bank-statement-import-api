# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import datetime
import logging

import requests

from odoo import Command, models
from odoo.tools import float_compare

from odoo.addons.account_statement_import_in_invoice.models.account_bank_statement_line import (
    TAX_DECIMAL_DIGITS,
)

logger = logging.getLogger(__name__)
TAXINT_MULTIPLIER = 10000
TIMEOUT = 30


class AccountJournal(models.Model):
    _inherit = "account.journal"

    # Documentation of the pivot format
    # result['lines'] is updated with the following dict:
    # {
    #     "attachments": [{
    #         "url": "https://xxx",
    #         "identifier': "01998a83-d209-7d4d-858e-a92e85f06648",
    #         "filename": "photo42.jpg",
    #     }],
    #     "in_invoice_vat_amount": 3.45,  # always positive
    #     "in_invoice_vat_rate": 20.0,  # main VAT rate of the transaction
    #     "in_invoice_expense_description": "Lunch with my dear customer",
    #     "in_invoice_card_code": "1242",
    #     "in_invoice_expense_categ_code": "restaurant",
    #     "in_invoice_force_invoice_date": "2025-09-28",  # string or datetime
    # }

    def _api_import_existing_line_bank_statement_line_fields(self):
        field_list = super()._api_import_existing_line_bank_statement_line_fields()
        field_list.append("move_id")
        return field_list

    def _api_import_prepare_existing_line(self, bank_statement_line, speedy):
        res = super()._api_import_prepare_existing_line(bank_statement_line, speedy)
        move_id = bank_statement_line["move_id"][0]
        speedy["existing_lines"][bank_statement_line["unique_import_id"]].update(
            {
                "move_id": move_id,
                "attachment_identifiers": [],
            }
        )
        speedy["move_id2unique_import_id"][move_id] = bank_statement_line[
            "unique_import_id"
        ]
        return res

    def _api_import_update_speedy(self, speedy):
        speedy["move_id2unique_import_id"] = {}
        res = super()._api_import_update_speedy(speedy)
        # Load cards
        card_read = (
            self.env["account.bank.statement.card"]
            .with_context(active_test=False)
            .search_read([("journal_id", "=", self.id)], ["code"])
        )
        card_code2id = {x["code"]: x["id"] for x in card_read}
        # Load existing attachment identifiers
        attach_identifier2id = {}  # Used for deleting attachments
        attach_read = self.env["ir.attachment"].search_read(
            [
                ("res_model", "=", "account.move"),
                ("res_id", "in", list(speedy["move_id2unique_import_id"].keys())),
                ("bank_statement_import_identifier", "!=", False),
            ],
            ["bank_statement_import_identifier", "res_id"],
        )
        for attach in attach_read:
            unique_import_id = speedy["move_id2unique_import_id"][attach["res_id"]]
            speedy["existing_lines"][unique_import_id]["attachment_identifiers"].append(
                attach["bank_statement_import_identifier"]
            )
            attach_identifier2id[attach["bank_statement_import_identifier"]] = attach[
                "id"
            ]
        # Load taxes
        taxes = self.env["account.tax"].search_read(
            self._api_import_purchase_tax_domain(), ["amount"]
        )
        tax_rateint2id = {}
        for tax in taxes:
            rate_int = int(
                round(tax["amount"] * TAXINT_MULTIPLIER)
            )  # amount digit precision = 4
            tax_rateint2id[rate_int] = tax["id"]
        speedy.update(
            {
                "card_code2id": card_code2id,
                "attach_identifier2id": attach_identifier2id,
                "tax_rateint2id": tax_rateint2id,
            }
        )
        return res

    def _api_import_purchase_tax_domain(self):
        domain = [
            ("company_id", "=", self.company_id.id),
            ("type_tax_use", "=", "purchase"),
            ("price_include", "=", False),
            ("amount_type", "=", "percent"),
            ("amount", ">", 0),
            ("unece_type_code", "=", "VAT"),
            ("unece_categ_code", "=", "S"),
        ]
        return domain

    def _api_import_prepare_card(self, pivot_line, speedy):
        vals = {
            "code": pivot_line["in_invoice_card_code"],
            "journal_id": self.id,
            "company_id": self.company_id.id,
        }
        return vals

    def _api_import_prepare_bank_statement_line(
        self, pivot_line, result, speedy, update_mode=False
    ):
        lvals = super()._api_import_prepare_bank_statement_line(
            pivot_line, result, speedy, update_mode=update_mode
        )
        card_code = pivot_line.get("in_invoice_card_code")
        if card_code:
            if card_code not in speedy["card_code2id"]:
                card = self.env["account.bank.statement.card"].create(
                    self._api_import_prepare_card(pivot_line, speedy)
                )
                self._api_import_info_log(
                    result, f"New card created with code '{card_code}' (ID {card.id})"
                )
                speedy["card_code2id"][card_code] = card.id
            lvals["in_invoice_card_id"] = speedy["card_code2id"][card_code]
        expcateg_code = pivot_line.get("in_invoice_expense_categ_code")
        if expcateg_code:
            if expcateg_code in speedy["expcateg_code2id"]:
                lvals["in_invoice_expense_categ_id"] = speedy["expcateg_code2id"][
                    expcateg_code
                ]
            else:
                self._api_import_warning_log(
                    result,
                    f"Expense category code '{expcateg_code}' doesn't exist "
                    f"for service {speedy['service']}",
                )
        analyticaccount_idents = pivot_line.get("in_invoice_analytic_account_idents")
        analytic_account_ids = []
        for analyticaccount_ident in analyticaccount_idents:
            if analyticaccount_ident in speedy["analyticaccount_ident2id"]:
                analytic_account_ids.append(
                    speedy["analyticaccount_ident2id"][analyticaccount_ident]["id"]
                )
                if not speedy["analyticaccount_ident2id"][analyticaccount_ident][
                    "account_id"
                ]:
                    account_name = speedy["analyticaccount_ident2id"][
                        analyticaccount_ident
                    ]["name"]
                    self._api_import_warning_log(
                        result,
                        f"Analytic account '{account_name}' is not "
                        f"mapped for service {speedy['service']}",
                    )
            else:
                self._api_import_warning_log(
                    result,
                    f"Analytic account identifier '{analyticaccount_ident}' doesn't "
                    f"exist for service {speedy['service']}",
                )

        lvals["in_invoice_analytic_account_ids"] = [Command.set(analytic_account_ids)]
        # for the moment, we consider that autoliq taxes are set by country-specific modules
        # that inherit this method
        in_invoice_tax_ids = []
        if (
            pivot_line.get("in_invoice_vat_rate")
            and pivot_line.get("in_invoice_vat_amount")
            and not speedy["journal_currency"].is_zero(
                pivot_line["in_invoice_vat_amount"]
            )
        ):
            rateint = int(round(pivot_line["in_invoice_vat_rate"] * TAXINT_MULTIPLIER))
            if rateint and rateint in speedy["tax_rateint2id"]:
                in_invoice_tax_ids = [speedy["tax_rateint2id"][rateint]]
        attachment_ids = []
        if pivot_line.get("attachments"):
            attachments_to_get = []  # list of dict
            # {'url': 'https://xxx', 'identifier': 'JLKDS'n 'filename' 'photo.jpg'}
            if update_mode:
                existing_line_attach_identifiers = speedy["existing_lines"][
                    pivot_line["unique_import_id"]
                ]["attachment_identifiers"]
                pivot_line_attach_identifiers = [
                    x["identifier"] for x in pivot_line["attachments"]
                ]
                attachment_identifiers_to_del = set(
                    existing_line_attach_identifiers
                ).difference(pivot_line_attach_identifiers)
                for attachment_identifier in attachment_identifiers_to_del:
                    attachment_ids.append(
                        Command.delete(
                            speedy["attach_identifier2id"][attachment_identifier]
                        )
                    )
                attachment_identifiers_to_get = set(
                    pivot_line_attach_identifiers
                ).difference(existing_line_attach_identifiers)
                for attach_pivot in pivot_line["attachments"]:
                    if attach_pivot["identifier"] in attachment_identifiers_to_get:
                        attachments_to_get.append(attach_pivot)
            else:
                attachments_to_get = pivot_line["attachments"]
            for attachment_pivot in attachments_to_get:
                attach_raw = self._api_import_get_attachment_from_url(
                    attachment_pivot["url"], result
                )
                if (
                    attach_raw
                    and attachment_pivot["identifier"]
                    and attachment_pivot["filename"]
                ):
                    attach_vals = {
                        "res_model": "account.move",
                        "raw": attach_raw,
                        "name": attachment_pivot["filename"],
                        "bank_statement_import_identifier": attachment_pivot[
                            "identifier"
                        ],
                    }
                    attachment_ids.append(Command.create(attach_vals))
        lvals.update(
            {
                "in_invoice_vat_amount": pivot_line.get("in_invoice_vat_amount"),
                "in_invoice_tax_ids": [Command.set(in_invoice_tax_ids)],
                "in_invoice_vat_rate": pivot_line.get("in_invoice_vat_rate"),
                "in_invoice_expense_description": pivot_line.get(
                    "in_invoice_expense_description"
                ),
                "in_invoice_force_invoice_date": pivot_line.get(
                    "in_invoice_force_invoice_date"
                ),
                "attachment_ids": attachment_ids,
            }
        )
        return lvals

    def _api_import_get_attachment_from_url(self, url, result):
        if not url:
            return None
        try:
            res = requests.get(url, verify=True, timeout=TIMEOUT)
        except Exception as e:
            self._api_import_error_log(
                result, f"API call to get attachment from {url} failed: {e}"
            )
            return None
        if res.status_code != 200:
            # let's see error_logs
            self._api_import_error_log(
                result,
                f"API call to get attachment from {url} returned an HTTP error code "
                f"{res.status_code}.",
            )
            return None
        if res.content:
            return res.content
        return None

    def _api_import_update_existing_line(self, pivot_line, result, speedy):
        res = super()._api_import_update_existing_line(pivot_line, result, speedy)
        lvals = self._api_import_prepare_bank_statement_line(
            pivot_line, result, speedy, update_mode=True
        )
        existing_line = speedy["existing_lines"][pivot_line["unique_import_id"]]
        st_line = self.env["account.bank.statement.line"].browse(existing_line["id"])
        st_line.write(lvals)
        result["updated_line_count"] += 1
        self._api_import_info_log(
            result,
            f"Updated existing unreconciled line ID {existing_line['id']} "
            f"dated {existing_line['date']} amount {existing_line['amount']} "
            f"label '{existing_line['payment_ref']}'",
        )
        return res

    def _api_import_check_update_pivot_line(self, pivot_line, result, speedy):
        res = super()._api_import_check_update_pivot_line(pivot_line, result, speedy)
        if pivot_line.get("in_invoice_force_invoice_date") and isinstance(
            pivot_line["in_invoice_force_invoice_date"], str
        ):
            try:
                pivot_line[
                    "in_invoice_force_invoice_date"
                ] = datetime.datetime.strptime(
                    pivot_line["in_invoice_force_invoice_date"], "%Y-%m-%d"
                )
            except ValueError:
                self._api_import_error_log(
                    result,
                    f"Field 'Force Invoice Date' has date "
                    f"'{pivot_line['in_invoice_force_invoice_date']}' "
                    f"as a string that doesn't respect format '%Y-%m-%d' "
                    f"in pivot line {pivot_line}",
                )
                return False
        field2type = {
            "in_invoice_vat_amount": (float, int),
            "in_invoice_vat_rate": (float, int),
            "in_invoice_expense_description": str,
            "in_invoice_card_code": str,
            "in_invoice_expense_categ_code": str,
            "in_invoice_force_invoice_date": (datetime.datetime, datetime.date),
        }
        for field, field_type in field2type.items():
            if pivot_line.get(field):
                if not isinstance(pivot_line[field], field_type):
                    self._api_import_error_log(
                        result,
                        f"Field {field} has value '{pivot_line[field]}' "
                        f"and type '{type(pivot_line[field])}' whereas the expected "
                        f"type is '{field_type}' in pivot line {pivot_line}",
                    )
                    return False
        if pivot_line.get("in_invoice_vat_amount"):
            pivot_line["in_invoice_vat_amount"] = abs(
                pivot_line["in_invoice_vat_amount"]
            )
        if (
            pivot_line.get("in_invoice_vat_rate")
            and float_compare(
                pivot_line["in_invoice_vat_rate"],
                0,
                precision_digits=TAX_DECIMAL_DIGITS,
            )
            < 0
        ):
            self._api_import_warning_log(
                result,
                f"Got a negative VAT rate "
                f"({pivot_line['in_invoice_vat_rate']}) on pivot line {pivot_line}: "
                f"VAT rate forced to 0",
            )
            pivot_line["in_invoice_vat_rate"] = 0
        return res
