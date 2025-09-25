# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import datetime
import logging

from odoo import Command, models
from odoo.tools import float_compare

from odoo.addons.account_statement_import_in_invoice.models.account_bank_statement_line import (
    TAX_DECIMAL_DIGITS,
)

logger = logging.getLogger(__name__)
TAXINT_MULTIPLIER = 10000


class AccountJournal(models.Model):
    _inherit = "account.journal"

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
        attach_method_name = f"_api_import_attachment_{speedy['service']}"
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
                "attach_method": getattr(self, attach_method_name),
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

    def _api_prepare_bank_statement_line(
        self, pivot_line, result, speedy, update_mode=False
    ):
        lvals = super()._api_prepare_bank_statement_line(
            pivot_line, result, speedy, update_mode=update_mode
        )
        card_code = pivot_line.get("in_invoice_card_code")
        if card_code:
            if card_code not in speedy["card_code2id"]:
                card = self.env["account.bank.statement.card"].create(
                    {
                        "code": card_code,
                        "journal_id": self.id,
                    }
                )
                result["logs"].append(
                    f"WARN New card created with code '{card_code}' (ID {card.id})"
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
                result["logs"].append(
                    f"WARN Expense category code '{expcateg_code}' doesn't exist "
                    f"for service {speedy['service']}"
                )
        # for the moment, we consider that autoliq taxes are set by country-specific modules
        # that inherit this method
        in_invoice_tax_ids = []
        if pivot_line.get("in_invoice_vat_rate"):
            rateint = int(round(pivot_line["in_invoice_vat_rate"] * TAXINT_MULTIPLIER))
            if rateint in speedy["tax_rateint2id"]:
                in_invoice_tax_ids = [speedy["tax_rateint2id"][rateint]]
        attachment_ids = []
        attachment_identifiers_to_get = []
        if update_mode:
            existing_line = speedy["existing_lines"][pivot_line["unique_import_id"]]
            attachment_identifiers_to_del = set(
                existing_line["attachment_identifiers"]
            ).difference(pivot_line["attachment_identifiers"])
            for attachment_identifier in attachment_identifiers_to_del:
                attachment_ids.append(
                    Command.delete(
                        speedy["attach_identifier2id"][attachment_identifier]
                    )
                )
            attachment_identifiers_to_get = set(
                pivot_line["attachment_identifiers"]
            ).difference(existing_line["attachment_identifiers"])
        else:
            attachment_identifiers_to_get = pivot_line["attachment_identifiers"]
        for attachment_identifier in attachment_identifiers_to_get:
            att_vals = self._api_import_get_attachment(
                attachment_identifier, result, speedy
            )
            if att_vals:
                attachment_ids.append(Command.create(att_vals))
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

    def _api_import_get_attachment(self, attachment_identifier, result, speedy):
        attach_tuple = speedy["attach_method"](attachment_identifier, result, speedy)
        if attach_tuple:
            filename, attach_raw = attach_tuple
            att_vals = {
                "res_model": "account.move",
                "raw": attach_raw,
                "name": filename,
                "bank_statement_import_identifier": attachment_identifier,
            }
            return att_vals
        return None

    def _api_import_update_existing_line(self, pivot_line, result, speedy):
        res = super()._api_import_update_existing_line(pivot_line, result, speedy)
        lvals = self._api_prepare_bank_statement_line(
            pivot_line, result, speedy, update_mode=True
        )
        existing_line = speedy["existing_lines"][pivot_line["unique_import_id"]]
        st_line = self.env["account.bank.statement.line"].browse(existing_line["id"])
        st_line.write(lvals)
        result["updated_line_count"] += 1
        result["logs"].append(
            f"INFO Updated existing unreconciled line ID {existing_line['id']} "
            f"dated {existing_line['date']} amount {existing_line['amount']} "
            f"label '{existing_line['payment_ref']}'"
        )
        return res

    def _api_import_check_update_pivot_line(
        self, pivot_line, result, journal_currency_code
    ):
        res = super()._api_import_check_update_pivot_line(
            pivot_line, result, journal_currency_code
        )
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
                result["logs"].append(
                    f"ERROR Field 'Force Invoice Date' has date "
                    f"'{pivot_line['in_invoice_force_invoice_date']}' "
                    f"as a string that doesn't respect format '%Y-%m-%d' "
                    f"in pivot line {pivot_line}"
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
                    result["logs"].append(
                        f"ERROR Field {field} has value '{pivot_line[field]}' "
                        f"and type '{type(pivot_line[field])}' whereas the expected "
                        f"type is '{field_type}' in pivot line {pivot_line}"
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
            result["logs"].append(
                f"WARN Got a negative VAT rate "
                f"({pivot_line['in_invoice_vat_rate']}) on pivot line {pivot_line}: "
                f"VAT rate forced to 0"
            )
            pivot_line["in_invoice_vat_rate"] = 0
        return res
