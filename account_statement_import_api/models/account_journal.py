# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import datetime
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import format_date, format_datetime

logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = "account.journal"

    statement_import_api_id = fields.Many2one(
        "account.statement.import.api", "Statement Import API", check_company=True
    )
    statement_import_api_service = fields.Selection(
        related="statement_import_api_id.service", store=True
    )
    statement_import_api_log_ids = fields.One2many(
        "account.statement.import.api.log",
        "journal_id",
        readonly=True,
        string="Statement Import API Logs",
    )
    statement_import_api_start_date = fields.Date(
        string="Import Start Date",
        help="The first bank statement API import will start from this date.",
    )
    statement_import_api_last_success = fields.Datetime(
        string="Last Import", help="Date and time of the last successful API import"
    )

    def __get_bank_statements_available_sources(self):
        res = super().__get_bank_statements_available_sources()
        res.insert(0, ("api", _("API")))
        return res

    @api.constrains(
        "statement_import_api_id",
        "bank_account_id",
        "statement_import_api_start_date",
        "statement_import_api_last_success",
    )
    def _check_statement_import_api(self):
        for journal in self:
            if journal.type == "bank" and journal.bank_statements_source == "api":
                if not journal.bank_account_id:
                    raise ValidationError(
                        _(
                            "The bank journal '%(journal)s' is configured with "
                            "Bank Feeds set to API, but the Account Number is not set.",
                            journal=journal.display_name,
                        )
                    )
                if not journal.statement_import_api_id:
                    raise ValidationError(
                        _(
                            "The bank journal '%(journal)s' is configured with "
                            "Bank Feeds set to API, so you must configure a "
                            "Statement Import API.",
                            journal=journal.display_name,
                        )
                    )
                if (
                    not journal.statement_import_api_last_success
                    and not journal.statement_import_api_start_date
                ):
                    raise ValidationError(
                        _(
                            "The bank journal '%(journal)s' is configured with "
                            "Bank Feeds set to API, so you must configure an "
                            "Import Start Date.",
                            journal=journal.display_name,
                        )
                    )
                if (
                    journal.statement_import_api_last_success
                    and journal.statement_import_api_start_date
                    and (
                        journal.statement_import_api_last_success.date()
                        + datetime.timedelta(1)
                    )
                    < journal.statement_import_api_start_date
                ):
                    raise ValidationError(
                        _(
                            "The bank journal '%(journal)s' is configured with "
                            "Import Start Date %(start_date)s, so the "
                            "Last Import Date %(last_success)s cannot be "
                            "prior to the Import Start Date.",
                            journal=journal.display_name,
                            start_date=format_date(
                                self.env, journal.statement_import_api_start_date
                            ),
                            last_success=format_datetime(
                                self.env, journal.statement_import_api_last_success
                            ),
                        )
                    )

    def _api_import_existing_line_bank_statement_line_fields(self):
        field_list = [
            "unique_import_id",
            "is_reconciled",
            "date",
            "amount",
            "payment_ref",
        ]
        return field_list

    def _api_import_prepare_existing_line(self, bank_statement_line, speedy):
        speedy["existing_lines"][bank_statement_line["unique_import_id"]] = {
            "id": bank_statement_line["id"],
            "is_reconciled": bank_statement_line["is_reconciled"],
            "date": bank_statement_line["date"],
            "amount": bank_statement_line["amount"],
            "payment_ref": bank_statement_line["payment_ref"],
        }

    def _api_import_update_speedy(self, speedy):
        """This method is designed to be inherited"""
        self.ensure_one()
        # Method _statement_line_import_speeddict() is defined in
        # the OCA module account_statement_import_base
        update_hook_speeddict = self._statement_line_import_speeddict()
        speedy.update(
            {
                "journal_currency": self.currency_id or self.company_id.currency_id,
                "existing_lines": {},
                "update_hook_speeddict": update_hook_speeddict,
            }
        )
        existing_lines_read = self.env["account.bank.statement.line"].search_read(
            [
                ("journal_id", "=", self.id),
                ("unique_import_id", "in", speedy["search_unique_import_ids"]),
            ],
            self._api_import_existing_line_bank_statement_line_fields(),
        )
        for line in existing_lines_read:
            self._api_import_prepare_existing_line(line, speedy)

    def _api_prepare_bank_statement_line(
        self, line_pivot, result, speedy, update_mode=False
    ):
        self.ensure_one()
        if update_mode:
            lvals = {}
        else:
            lvals = {
                "unique_import_id": line_pivot["unique_import_id"],
                "journal_id": self.id,
                "date": line_pivot["date"],
                "amount": line_pivot["amount"],
                "payment_ref": line_pivot["payment_ref"],
            }
        return lvals

    def _api_import_bank_statement_lines(self, speedy):
        self.ensure_one()
        log_obj = self.env["account.statement.import.api.log"]
        logger.info("Start bank statement import API of journal %s", self.display_name)
        # raise for cases that should never happen because that are python constrains on it
        if (
            not self.statement_import_api_last_success
            and not self.statement_import_api_start_date
        ):
            raise UserError(
                _(
                    "Import Start Date is not set on journal '%(journal)s'.",
                    journal=self.display_name,
                )
            )
        result = {
            "lines": [],
            "updated_line_count": 0,
            "logs": [],
        }
        # result['lines'] will contain a list of bank statement lines in pivot format
        # below:
        # {
        #   'date': '2025-08-24',  # string or datetime format
        #   'amount': -60.00,  # negative for debits. In the currency of the journal.
        #   'currency_code': 'EUR',  # currency of the 'amount' field (optional).
        #                              Will allow the generic code below to check that
        #                              it is the currency of the journal
        #   'payment_ref': 'VIR SEPA ODOO COMMUNITY ASSOCIATION',
        #   'unique_import_id': 'DSIVYIUC1242',  # will be updated by
        #                               _statement_line_import_update_unique_import_id()
        #                                        to the unique_import_id stored by odoo
        # }

        method_name = f"_api_import_{speedy['service']}"
        method = getattr(self, method_name)
        method(result, speedy)

        new_line_vals = []
        if result["lines"] and not any(
            [log.startswith("ERROR ") for log in result["logs"]]
        ):
            speedy["search_unique_import_ids"] = []
            for pivot_line in result["lines"]:
                # Update pivot_line['unique_import_id'] to have the "full" value
                self._statement_line_import_update_unique_import_id(
                    pivot_line, self.bank_account_id.sanitized_acc_number
                )
                speedy["search_unique_import_ids"].append(
                    pivot_line["unique_import_id"]
                )
            self._api_import_update_speedy(speedy)
            journal_currency_code = speedy["journal_currency"].name
            self.write({"statement_import_api_last_success": fields.Datetime.now()})
            existing_lines = speedy["existing_lines"]
            for pivot_line in result["lines"]:
                check_res = self._api_import_check_update_pivot_line(
                    pivot_line, result, journal_currency_code
                )
                if not check_res:
                    continue
                if (
                    self.statement_import_api_start_date
                    and pivot_line["date"] < self.statement_import_api_start_date
                ):
                    result["logs"].append(
                        f"INFO Skipped retreived transaction dated "
                        f"{pivot_line['date']} amount {pivot_line['amount']} "
                        f"label {pivot_line['payment_ref']} because it is "
                        f"before the start import date {self.statement_import_api_start_date}"
                    )
                elif pivot_line["unique_import_id"] in existing_lines:
                    existing_line = existing_lines[pivot_line["unique_import_id"]]
                    if existing_line["is_reconciled"]:
                        result["logs"].append(
                            f"INFO Skipped existing reconciled line ID "
                            f"{existing_line['id']} dated {existing_line['date']} "
                            f"amount {existing_line['amount']} "
                            f"label '{existing_line['payment_ref']}'"
                        )
                    elif speedy.get("update_existing_bank_statement_lines"):
                        self._api_import_update_existing_line(
                            pivot_line, result, speedy
                        )
                    else:
                        result["logs"].append(
                            f"INFO Skipped existing unreconciled line ID "
                            f"{existing_line['id']} dated {existing_line['date']} "
                            f"amount {existing_line['amount']} "
                            f"label '{existing_line['payment_ref']}'"
                        )
                else:  # New bank statement line to create
                    lvals = self._api_prepare_bank_statement_line(
                        pivot_line, result, speedy
                    )
                    # The method _statement_line_import_update_hook() is defined
                    # in the OCA module account_statement_import_base
                    self._statement_line_import_update_hook(
                        lvals, speedy["update_hook_speeddict"]
                    )
                    new_line_vals.append(lvals)
                    result["logs"].append(
                        f"INFO Created new line dated {lvals['date']} "
                        f"amount {lvals['amount']} label '{lvals['payment_ref']}'"
                    )
            if new_line_vals and not any(
                [log.startswith("ERROR ") for log in result["logs"]]
            ):
                self.env["account.bank.statement.line"].create(new_line_vals)

        result["new_line_count"] = len(new_line_vals)
        logger.info(
            "%d bank statement lines created. %d updated.",
            result["new_line_count"],
            result["updated_line_count"],
        )
        log_vals = self._api_import_prepare_log(result, speedy)
        log = log_obj.create(log_vals)
        logger.debug("Bank statement import log created ID %d", log.id)
        logger.info("End of bank statement import API of journal %s", self.display_name)
        return log

    def _api_import_prepare_log(self, result, speedy):
        logs = []
        for log in result["logs"]:
            if log.startswith("INFO "):
                msg = log[5:]
                logs.append(
                    f'<span style="color: green; font-weight: bold">'
                    f"INFO </span>{msg}"
                )
                logger.info(msg)
            elif log.startswith("WARN "):
                msg = log[5:]
                logs.append(
                    f'<span style="color: orange; font-weight: bold">'
                    f"WARN </span>{msg}"
                )
                logger.warning(msg)
            elif log.startswith("ERROR "):
                msg = log[6:]
                logs.append(
                    f'<span style="color: red; font-weight: bold">'
                    f"ERROR </span>{msg}"
                )
                logger.error(msg)
            else:  # Should not happen
                logs.append(log)
        has_error = any([log.startswith("ERROR ") for log in result["logs"]])
        if has_error:
            status = "failure"
        else:
            has_warn = any([log.startswith("WARN ") for log in result["logs"]])
            if has_warn:
                status = "success_warn"
            else:
                status = "success"
        log_vals = {
            "journal_id": self.id,
            "statement_import_api_id": speedy["statement_import_api_id"],
            "status": status,
            "new_line_count": result["new_line_count"],
            "updated_line_count": result["updated_line_count"],
            "logs": "<br>".join(logs),
        }
        return log_vals

    def _api_import_update_existing_line(self, pivot_line, result, speedy):
        """This method is inherited in account_statement_import_in_invoice_api"""
        self.ensure_one()

    def _api_import_check_update_pivot_line(
        self, pivot_line, result, journal_currency_code
    ):
        required_field2type = {
            "date": (datetime.datetime, datetime.date),
            "amount": (float, int),
            "unique_import_id": str,
            "payment_ref": str,
        }

        for required_field in required_field2type.keys():
            if not pivot_line.get(required_field):
                result["logs"].append(
                    f"ERROR Field {required_field} is missing in pivot line {pivot_line}"
                )
                return False
        # for "date" key, we accept both string and date object.
        # If it's a string, we convert to date object
        if isinstance(pivot_line["date"], str):
            try:
                pivot_line["date"] = datetime.datetime.strptime(
                    pivot_line["date"], "%Y-%m-%d"
                ).date()
            except ValueError:
                result["logs"].append(
                    f"ERROR Date '{pivot_line['date']}' is a string that doesn't "
                    f"respect format '%Y-%m-%d' in pivot line {pivot_line}"
                )
                return False

        for field, field_type in required_field2type.items():
            if not isinstance(pivot_line[field], field_type):
                result["logs"].append(
                    f"ERROR Field {field} has value '{pivot_line[field]}' "
                    f"and type '{type(pivot_line[field])}' whereas the expected type "
                    f"is '{field_type}' in pivot line {pivot_line}"
                )
                return False
        if (
            pivot_line.get("currency_code")
            and pivot_line["currency_code"].upper() != journal_currency_code
        ):
            result["logs"].append(
                f"ERROR Transaction is in currency {pivot_line['currency_code']} "
                f"whereas the bank journal {self.display_name} is in currency "
                f"{journal_currency_code} in pivot line {pivot_line}"
            )
            return False
        return True

    def api_import_bank_statement_lines_button(self):
        self.ensure_one()
        if not self.statement_import_api_id:
            raise UserError(
                _(
                    "Journal '%s' is not configured to import bank statements "
                    "via API."
                )
                % self.display_name
            )
        speedy = self.statement_import_api_id._prepare_speedy()
        log = self._api_import_bank_statement_lines(speedy)
        if log.status == "failure":
            title = _("Sync Failed")
            message = (
                _("See error log on Statement Import API '%s'.")
                % log.statement_import_api_id.display_name
            )
            ptype = "danger"
        else:
            title = _("Successful Sync")
            if log.status == "success_warn":
                ptype = "warning"
                message = (
                    _("Sync with warning(s), cf last log on Statement Import API '%s'.")
                    % log.statement_import_api_id.display_name
                )
            else:
                ptype = "success"
                if log.new_line_count > 1:
                    message = _("%s bank statement lines created.") % log.new_line_count
                elif log.new_line_count == 1:
                    message = _("1 bank statement line created.")
                else:
                    message = _("No new bank statement lines.")
                if log.updated_line_count:
                    message += " " + _("%s updated.") % log.updated_line_count

        action = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": ptype,
                "title": title,
                "message": message,
            },
        }
        return action

    def _api_import_timestamp_iso8601_to_date(
        self, timestamp, speedy, timestamp_tz=False
    ):
        if not timestamp:
            return False
        timestamp_dt = datetime.datetime.fromisoformat(timestamp)
        # if timestamp contains TZ info, timestamp_dt is datetime aware
        # if timestamp doesn't contain any TZ info, timestamp_dt is datetime naive
        #   in this case, we read the TZ from timestamp_tz (if it' false, we consider
        #   it is the TZ configured on account.statement.import.api)
        if not timestamp_dt.tzinfo:
            if timestamp_tz:
                timestamp_dt = timestamp_tz.localize(timestamp_dt)
            else:
                timestamp_dt = speedy["tz"].localize(timestamp_dt)
        # switch to our TZ and convert to date
        timestamp_dt_our_tz = timestamp_dt.astimezone(speedy["tz"])
        date_dt = timestamp_dt_our_tz.date()
        return date_dt
