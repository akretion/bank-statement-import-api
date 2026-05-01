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

from .account_statement_import_api import TAXINT_MULTIPLIER

logger = logging.getLogger(__name__)
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
    #     "in_invoice_receipt_lost": False,  # bool
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

    def _api_import_set_existing_lines(self, search_unique_import_ids, speedy):
        res = super()._api_import_set_existing_lines(search_unique_import_ids, speedy)
        # Load existing attachment identifiers
        # We must have the code there (and not in _api_import_update_speedy())
        # because we need to have the values in speedy["move_id2unique_import_id"]
        attach_read = self.env["ir.attachment"].search_read(
            [
                ("res_model", "=", "account.move"),
                ("res_id", "in", list(speedy["move_id2unique_import_id"].keys())),
                ("bank_statement_import_identifier", "!=", False),
            ],
            ["bank_statement_import_identifier", "res_id"],
        )
        for attach in attach_read:
            move_id = attach["res_id"]
            unique_import_id = speedy["move_id2unique_import_id"][move_id]
            speedy["existing_lines"][unique_import_id]["attachment_identifiers"].append(
                attach["bank_statement_import_identifier"]
            )
            speedy["attach_identifier2id"][
                attach["bank_statement_import_identifier"]
            ] = attach["id"]
        return res

    def _api_import_update_speedy(self, speedy):
        res = super()._api_import_update_speedy(speedy)
        # Load cards
        card_read = (
            self.env["account.bank.statement.card"]
            .with_context(active_test=False)
            .search_read([("journal_id", "=", self.id)], ["code"])
        )
        card_code2id = {x["code"]: x["id"] for x in card_read}
        speedy.update(
            {
                "card_code2id": card_code2id,
                "move_id2unique_import_id": {},
                "attach_identifier2id": {},  # used to handle attachment deletion
            }
        )
        return res

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
                speedy["log_obj"]._info_log(
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
                speedy["log_obj"]._warning_log(
                    result,
                    f"Expense category code '{expcateg_code}' doesn't exist "
                    f"for service {speedy['service']}",
                )
        if pivot_line["payment_ref"] in speedy["payment_ref2partner_id"]:
            lvals["partner_id"] = speedy["payment_ref2partner_id"][
                pivot_line["payment_ref"]
            ]
        bs_analytic_account_idents = pivot_line.get(
            "in_invoice_analytic_account_idents"
        )
        bs_ana_account_ident2vals = speedy.get("bs_analytic_account_ident2vals")
        if bs_analytic_account_idents and bs_ana_account_ident2vals:
            bs_analytic_account_ids = []
            for bs_ana_acc_ident in bs_analytic_account_idents:
                if bs_ana_acc_ident not in bs_ana_account_ident2vals:
                    speedy["log_obj"]._warning_log(
                        result,
                        f"Bank statement analytic account identifier "
                        f"'{bs_ana_acc_ident}' doesn't exist in Odoo. "
                        "Click on the button "
                        "'Get/Update Bank Statement Analytic Accounts'.",
                    )
                    continue
                bs_analytic_account_ids.append(
                    bs_ana_account_ident2vals[bs_ana_acc_ident]["id"]
                )
                if not bs_ana_account_ident2vals[bs_ana_acc_ident][
                    "analytic_account_id"
                ]:
                    bs_ana_acc_dname = bs_ana_account_ident2vals[bs_ana_acc_ident][
                        "display_name"
                    ]
                    speedy["log_obj"]._warning_log(
                        result,
                        f"Bank statement analytic account '{bs_ana_acc_dname}' is not "
                        f"mapped to an Odoo analytic account",
                    )

            lvals["in_invoice_bank_statement_analytic_account_ids"] = [
                Command.set(bs_analytic_account_ids)
            ]
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
                    attachment_pivot["url"], result, speedy
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
        else:
            attachment_ids.append(Command.clear())  # del all attachments
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
                "in_invoice_receipt_lost": pivot_line.get("in_invoice_receipt_lost"),
                "attachment_ids": attachment_ids,
            }
        )
        return lvals

    def _api_import_get_attachment_from_url(self, url, result, speedy):
        if not url:
            return None
        try:
            res = requests.get(url, verify=True, timeout=TIMEOUT)
        except Exception as e:
            speedy["log_obj"]._error_log(
                result, f"API call to get attachment from {url} failed: {e}"
            )
            return None
        if res.status_code != 200:
            # let's see error_logs
            speedy["log_obj"]._error_log(
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
        speedy["log_obj"]._info_log(
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
                speedy["log_obj"]._error_log(
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
                    speedy["log_obj"]._error_log(
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
            speedy["log_obj"]._warning_log(
                result,
                f"Got a negative VAT rate "
                f"({pivot_line['in_invoice_vat_rate']}) on pivot line {pivot_line}: "
                f"VAT rate forced to 0",
            )
            pivot_line["in_invoice_vat_rate"] = 0
        return res
