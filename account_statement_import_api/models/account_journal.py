# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import datetime
import logging
import sys

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import format_amount, format_date, format_datetime

# Backport of datetime.fromisoformat() for python < 3.11
# pip install backports-datetime-fromisoformat
if sys.version_info < (3, 11):
    from backports.datetime_fromisoformat import MonkeyPatch

    MonkeyPatch.patch_fromisoformat()

logger = logging.getLogger(__name__)


class AccountJournal(models.Model):
    _inherit = "account.journal"

    statement_import_api_id = fields.Many2one(
        "account.statement.import.api",
        "Statement Import API",
        check_company=True,
        tracking=True,
        compute="_compute_statement_import_api_id",
        store=True,
        readonly=False,
        precompute=True,
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
        compute="_compute_statement_import_api_start_date",
        store=True,
        readonly=False,
        precompute=True,
        help="The first bank statement API import will start from this date.",
    )
    statement_import_api_last_success = fields.Datetime(
        string="Last Import", help="Date and time of the last successful API import"
    )
    statement_import_api_account_id = fields.Many2one(
        "account.statement.import.api.account",
        string="API Bank Account",
        check_company=True,
        copy=False,
        tracking=True,
        compute="_compute_statement_import_api_account_id",
        store=True,
        readonly=False,
        precompute=True,
        domain="[('statement_import_api_id', '=', statement_import_api_id)]",
    )
    statement_import_api_account_identifier = fields.Char(
        related="statement_import_api_account_id.identifier",
        string="Account Identifier",
        store=True,
    )
    statement_import_api_connector_id = fields.Many2one(
        related="statement_import_api_account_id.connector_id",
        store=True,
    )
    statement_import_api_connector_auth_expiry_date = fields.Date(
        related="statement_import_api_account_id.connector_id.auth_expiry_date",
        string="Account Auth Expiry",
        store=True,
    )
    statement_import_api_connector_sync_status = fields.Selection(
        related="statement_import_api_account_id.connector_id.sync_status",
        string="Sync Status",
        store=True,
    )
    statement_import_api_connector_auth_expiry_warn_type = fields.Selection(
        related="statement_import_api_account_id.connector_id.auth_expiry_warn_type",
    )

    _sql_constraints = [
        (
            "statement_import_api_account_uniq",
            "unique(statement_import_api_account_id)",
            "This API bank account is already selected on another journal.",
        )
    ]

    def __get_bank_statements_available_sources(self):
        res = super().__get_bank_statements_available_sources()
        res.insert(0, ("api", _("API")))
        return res

    @api.depends("type", "bank_statements_source")
    def _compute_statement_import_api_id(self):
        for journal in self:
            if journal.type != "bank" or journal.bank_statements_source != "api":
                journal.statement_import_api_id = False

    @api.depends("statement_import_api_id")
    def _compute_statement_import_api_account_id(self):
        for journal in self:
            statement_import_api_account_id = False
            if (
                journal.statement_import_api_id
                and not journal.statement_import_api_account_id
                and journal.bank_account_id
            ):
                acc_number = journal.bank_account_id.sanitized_acc_number
                for api_account in journal.statement_import_api_id.api_account_ids:
                    if (
                        api_account.account_number
                        and api_account.account_number == acc_number
                    ):
                        statement_import_api_account_id = api_account.id
                        break
            journal.statement_import_api_account_id = statement_import_api_account_id

    @api.depends("statement_import_api_id")
    def _compute_statement_import_api_start_date(self):
        stline_obj = self.env["account.bank.statement.line"]
        for journal in self:
            start_date = False
            journal_id = journal._origin.id
            if journal.statement_import_api_id and journal_id:
                last_st_line = stline_obj.search_read(
                    [
                        ("journal_id", "=", journal_id),
                    ],
                    ["date"],
                    order="date desc",
                    limit=1,
                )
                if last_st_line:
                    start_date = last_st_line[0]["date"] + datetime.timedelta(1)
            journal.statement_import_api_start_date = start_date

    @api.constrains(
        "statement_import_api_id",
        "currency_id",
        "statement_import_api_account_id",
        "statement_import_api_start_date",
        "statement_import_api_last_success",
    )
    def _check_statement_import_api(self):
        for journal in self:
            if journal.type == "bank" and journal.bank_statements_source == "api":
                if not journal.statement_import_api_id:
                    continue
                if (
                    journal.statement_import_api_id
                    and not journal.statement_import_api_account_id
                ):
                    raise ValidationError(
                        _(
                            "The API Bank Account is not set on journal '%(journal)s' "
                            "which is configured with Bank Feeds set to API and "
                            "Statement Import API '%(import_api)s'.",
                            journal=journal.display_name,
                            import_api=journal.statement_import_api_id.display_name,
                        )
                    )
                if (
                    journal.statement_import_api_account_id
                    and journal.statement_import_api_account_id.currency_id
                ):
                    api_account_currency = (
                        journal.statement_import_api_account_id.currency_id
                    )
                    journal_currency = (
                        journal.currency_id or journal.company_id.currency_id
                    )
                    if api_account_currency != journal_currency:
                        raise ValidationError(
                            _(
                                "The bank journal '%(journal)s' is in currency "
                                "%(journal_currency)s whereas the API Bank Account "
                                "is in currency %(api_account_currency)s.",
                                journal=journal.display_name,
                                journal_currency=journal_currency.name,
                                api_account_currency=api_account_currency.name,
                            )
                        )
                api_account = journal.statement_import_api_account_id
                if (
                    api_account
                    and api_account.statement_import_api_id
                    != journal.statement_import_api_id
                ):
                    api_account_st_import_api_dname = (
                        api_account.statement_import_api_id.display_name
                    )
                    raise ValidationError(
                        _(
                            "The bank journal '%(journal)s' is configured with "
                            "the statement import API '%(statement_import_api)s' "
                            "and the API bank account '%(api_account)s' "
                            "but the API bank account is linked to another statement "
                            "import API ('%(api_account_statement_import_api)s').",
                            journal=journal.display_name,
                            statement_import_api=journal.statement_import_api_id.display_name,
                            api_account=api_account.display_name,
                            api_account_statement_import_api=api_account_st_import_api_dname,
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
        journal_currency = self.currency_id or self.company_id.currency_id
        speedy.update(
            {
                "journal_currency": journal_currency,
                "journal_currency_code": journal_currency.name,
                "update_hook_speeddict": update_hook_speeddict,
                "bank_account_number": self.bank_account_id.sanitized_acc_number,
            }
        )

    def _api_import_set_existing_lines(self, search_unique_import_ids, speedy):
        speedy["existing_lines"] = {}
        existing_lines_read = self.env["account.bank.statement.line"].search_read(
            [
                ("journal_id", "=", self.id),
                ("unique_import_id", "in", search_unique_import_ids),
            ],
            self._api_import_existing_line_bank_statement_line_fields(),
        )
        for line in existing_lines_read:
            self._api_import_prepare_existing_line(line, speedy)

    def _api_import_prepare_bank_statement_line(
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
                "transaction_type": line_pivot.get("transaction_type"),
            }
            if line_pivot.get("foreign_currency_amount") and line_pivot.get(
                "foreign_currency_code"
            ):
                foreign_currency_code = line_pivot["foreign_currency_code"].upper()
                if foreign_currency_code != speedy["journal_currency_code"]:
                    if foreign_currency_code in speedy["currency_code2id"]:
                        lvals.update(
                            {
                                "foreign_currency_id": speedy["currency_code2id"][
                                    foreign_currency_code
                                ],
                                "amount_currency": line_pivot[
                                    "foreign_currency_amount"
                                ],
                            }
                        )
                    else:
                        msg = (
                            f"Currency {foreign_currency_code} is inactive or "
                            f"doesn't exist in Odoo. Found on transaction "
                            f"dated {lvals['date']} amount {lvals['amount']} "
                            f"label '{lvals['payment_ref']}. Transaction imported without "
                            f"the amount in foreign currency "
                            f"{line_pivot['foreign_currency_amount']}."
                        )
                        speedy["log_obj"]._warning_log(result, msg)
        return lvals

    def _api_import_bank_statement_lines(self, account_ident2vals, speedy):
        self.ensure_one()
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
        self._api_import_update_speedy(speedy)
        # result['lines'] will contain a list of bank statement lines in pivot format
        # below:
        # {
        #   'date': '2025-08-24',  # string or datetime format
        #   'amount': -60.00,  # negative for debits. In the currency of the journal.
        #   'currency_code': 'EUR',  # currency of the 'amount' field (optional).
        #                              Will allow the generic code below to check that
        #                              it is the currency of the journal
        #   'payment_ref': 'VIR SEPA ODOO COMMUNITY ASSOCIATION',
        #   'transaction_type': 'transfer',  # char field
        #   'unique_import_id': 'DSIVYIUC1242',  # will be updated by
        #                               _statement_line_import_update_unique_import_id()
        #                                        to the unique_import_id stored by odoo
        #   'foreign_currency_amount': -68.47,  # amount in foreign currency
        #   'foreign_currency_code': 'USD',  # foreign currency code
        #   'last_update_dt': datetime.datetime(2026, 2, 2, 16, 31, 29, 483518),  # last
        #      # update datetime (datetime naive in UTC): used to set
        #      # statement_import_api_last_success if
        #      # speedy['service_info'].get('last_success_source') == "last_update_dt"
        #      # The field is required in this case.
        #   'to_delete': True,  # if set to True (very rare), it means we should delete
        #      # the bank statement line. If it hasn't been reconciled yet it odoo, we
        #      # deleted it ; otherwise, we set a big warning.
        # }

        method_name = f"_api_import_{speedy['service']}"
        method = getattr(self, method_name)
        method(result, speedy)

        new_line_vals = []
        if result["lines"] and not any(
            [log_type == "error" for log_type, msg in result["logs"]]
        ):
            last_success_source = speedy["service_info"].get("last_success_source")
            search_unique_import_ids = []
            if last_success_source == "last_update_dt":
                last_success_dt = self.statement_import_api_last_success
            else:
                last_success_dt = fields.Datetime.now()
            for pivot_line in result["lines"]:
                # Update pivot_line['unique_import_id'] to have the "full" value
                self._statement_line_import_update_unique_import_id(
                    pivot_line, self.bank_account_id.sanitized_acc_number
                )
                search_unique_import_ids.append(pivot_line["unique_import_id"])
                if last_success_source == "last_update_dt":
                    if not last_success_dt or (
                        last_success_dt
                        and pivot_line["last_update_dt"] > last_success_dt
                    ):
                        last_success_dt = pivot_line["last_update_dt"]

            self._api_import_set_existing_lines(search_unique_import_ids, speedy)
            self.write({"statement_import_api_last_success": last_success_dt})
            existing_lines = speedy["existing_lines"]
            for pivot_line in result["lines"]:
                check_res = self._api_import_check_update_pivot_line(
                    pivot_line, result, speedy
                )
                if not check_res:
                    continue
                if (
                    self.statement_import_api_start_date
                    and pivot_line["date"] < self.statement_import_api_start_date
                ):
                    speedy["log_obj"]._info_log(
                        result,
                        f"Skipped retreived transaction dated "
                        f"{pivot_line['date']} amount {pivot_line['amount']} "
                        f"label {pivot_line['payment_ref']} because it is "
                        f"before the start import date {self.statement_import_api_start_date}",
                    )
                elif pivot_line["unique_import_id"] in existing_lines:
                    existing_line = existing_lines[pivot_line["unique_import_id"]]
                    if pivot_line.get("to_delete"):
                        if existing_line["is_reconciled"]:
                            speedy["log_obj"]._error_log(
                                result,
                                f"Existing reconciled line ID "
                                f"{existing_line['id']} dated {existing_line['date']} "
                                f"amount {existing_line['amount']} "
                                f"label '{existing_line['payment_ref']}' is "
                                "marked as 'to_delete', but odoo can't delete it "
                                "because it is already reconciled. You must handle "
                                "it manually.",
                            )
                        else:
                            speedy["log_obj"]._warning_log(
                                result,
                                f"Deleted existing unreconciled line ID "
                                f"{existing_line['id']} dated {existing_line['date']} "
                                f"amount {existing_line['amount']} "
                                f"label '{existing_line['payment_ref']}' because "
                                "it is marked as 'to_delete'",
                            )
                            bank_statement_line = self.env[
                                "account.bank.statement.line"
                            ].browse(existing_line["id"])
                            bank_statement_line.unlink()
                        continue
                    if existing_line["is_reconciled"]:
                        speedy["log_obj"]._info_log(
                            result,
                            f"Skipped existing reconciled line ID "
                            f"{existing_line['id']} dated {existing_line['date']} "
                            f"amount {existing_line['amount']} "
                            f"label '{existing_line['payment_ref']}'",
                        )
                    elif speedy.get("update_existing_bank_statement_lines"):
                        self._api_import_update_existing_line(
                            pivot_line, result, speedy
                        )
                    else:
                        speedy["log_obj"]._info_log(
                            result,
                            f"Skipped existing unreconciled line ID "
                            f"{existing_line['id']} dated {existing_line['date']} "
                            f"amount {existing_line['amount']} "
                            f"label '{existing_line['payment_ref']}'",
                        )
                else:  # New bank statement line to create
                    if pivot_line.get("to_delete"):
                        speedy["log_obj"]._info_log(
                            result,
                            f"Skipped line dated {pivot_line['date']} "
                            f"amount {pivot_line['amount']} label "
                            f"'{pivot_line['payment_ref']}' because it is marked "
                            "as 'to_delete' and it was not in Odoo yet.",
                        )
                        continue
                    lvals = self._api_import_prepare_bank_statement_line(
                        pivot_line, result, speedy
                    )
                    # The method _statement_line_import_update_hook() is defined
                    # in the OCA module account_statement_import_base
                    self._statement_line_import_update_hook(
                        lvals, speedy["update_hook_speeddict"]
                    )
                    new_line_vals.append(lvals)
                    speedy["log_obj"]._info_log(
                        result,
                        f"Created new line dated {lvals['date']} "
                        f"amount {lvals['amount']} label '{lvals['payment_ref']}'",
                    )
            if new_line_vals and not any(
                [log_type == "error" for log_type, msg in result["logs"]]
            ):
                self.env["account.bank.statement.line"].create(new_line_vals)

        result["new_line_count"] = len(new_line_vals)
        logger.info(
            "%d bank statement lines created. %d updated.",
            result["new_line_count"],
            result["updated_line_count"],
        )
        self._api_import_check_balance(account_ident2vals, result, speedy)
        log = speedy["log_obj"]._create_log(
            "statement_line", result, speedy, journal_id=self.id
        )
        logger.info("End of bank statement import API of journal %s", self.display_name)
        return log

    def _api_import_update_existing_line(self, pivot_line, result, speedy):
        """This method is inherited in account_statement_import_in_invoice_api"""
        self.ensure_one()

    def _api_import_check_update_pivot_line(self, pivot_line, result, speedy):
        required_field2type = {
            "date": (datetime.datetime, datetime.date),
            "amount": (float, int),
            "unique_import_id": str,
            "payment_ref": str,
        }

        for required_field in required_field2type.keys():
            if not pivot_line.get(required_field):
                speedy["log_obj"]._error_log(
                    result,
                    f"Field {required_field} is missing in pivot line {pivot_line}",
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
                speedy["log_obj"]._error_log(
                    result,
                    f"Date '{pivot_line['date']}' is a string that doesn't "
                    f"respect format '%Y-%m-%d' in pivot line {pivot_line}",
                )
                return False

        for field, field_type in required_field2type.items():
            if not isinstance(pivot_line[field], field_type):
                speedy["log_obj"]._error_log(
                    result,
                    f"Field {field} has value '{pivot_line[field]}' "
                    f"and type '{type(pivot_line[field])}' whereas the expected type "
                    f"is '{field_type}' in pivot line {pivot_line}",
                )
                return False
        if (
            pivot_line.get("currency_code")
            and pivot_line["currency_code"].upper() != speedy["journal_currency_code"]
        ):
            speedy["log_obj"]._error_log(
                result,
                f"Transaction is in currency {pivot_line['currency_code']} "
                f"whereas the bank journal {self.display_name} is in currency "
                f"{speedy['journal_currency_code']} in pivot line {pivot_line}",
            )
            return False
        return True

    def _api_import_check_balance(self, account_ident2vals, result, speedy):
        accounting_bal = self._api_import_get_accounting_balance(speedy)
        account_ident = self.statement_import_api_account_id.identifier
        if accounting_bal is None:
            msg = (
                f"Field 'default_account_id' is not set on journal {self.display_name}"
            )
            speedy["log_obj"]._warning_log(result, msg)
        elif account_ident not in account_ident2vals:
            msg = f"Account identifier {account_ident} is not in account_ident2vals"
            speedy["log_obj"]._warning_log(result, msg)
        elif "balance" not in account_ident2vals[account_ident]:
            msg = f"Balance not available for account identifier {account_ident}"
            speedy["log_obj"]._info_log(result, msg)
        else:
            currency = speedy["journal_currency"]
            bank_bal = account_ident2vals[account_ident]["balance"]
            bank_currency_code = account_ident2vals[account_ident].get("currency_code")
            currency_mismatch = False
            if bank_currency_code:
                bank_currency_id = speedy["currency_code2id"].get(bank_currency_code)
                if bank_currency_id and bank_currency_id != currency.id:
                    currency_mismatch = True
                    msg = (
                        f"Currency of bank journal ({currency.name}) is different "
                        f"from currency reported by API ({bank_currency_code}). "
                        "This should never happen!"
                    )
                    speedy["log_obj"]._warning_log(result, msg)
            if not currency_mismatch:
                fcompare = currency.compare_amounts(accounting_bal, bank_bal)
                accounting_bal_fmt = format_amount(self.env, accounting_bal, currency)
                if not fcompare:
                    msg = f"Accounting balance = bank balance ({accounting_bal_fmt})"
                    speedy["log_obj"]._info_log(result, msg)
                else:
                    bank_bal_fmt = format_amount(self.env, bank_bal, currency)
                    diff_fmt = format_amount(
                        self.env, accounting_bal - bank_bal, currency
                    )
                    msg = (
                        f"Accounting balance ({accounting_bal_fmt}) is different "
                        f"from bank balance ({bank_bal_fmt}). Difference: {diff_fmt}"
                    )
                    speedy["log_obj"]._warning_log(result, msg)

    def _api_import_get_accounting_balance(self, speedy):
        self.ensure_one()
        bal = None
        if self.default_account_id:
            rg_res = self.env["account.move.line"].read_group(
                [
                    ("account_id", "=", self.default_account_id.id),
                    ("company_id", "=", self.company_id.id),
                    ("parent_state", "=", "posted"),
                ],
                ["balance"],
                [],
            )
            bal = rg_res and rg_res[0]["balance"] or 0
        return bal

    def api_import_bank_statement_lines_button(self):
        self.ensure_one()
        import_api = self.statement_import_api_id
        if not import_api:
            raise UserError(
                _(
                    "Journal '%s' is not configured to import bank statements "
                    "via API.",
                    self.display_name,
                )
            )
        speedy = import_api._prepare_speedy()
        result = {"logs": []}
        all_logs = speedy["log_obj"]
        account_ident2vals = import_api._update_connector_and_get_balance(
            result, speedy
        )
        log = speedy["log_obj"]._create_log("other", result, speedy)
        if log:
            all_logs |= log
        log = self._api_import_bank_statement_lines(account_ident2vals, speedy)
        if log:
            all_logs |= log
        action = all_logs._prepare_notification_action()
        return action

    def _api_import_timestamp_iso8601_to_datetime_aware(
        self, timestamp, speedy, timestamp_tz=False
    ):
        if not timestamp:
            return False
        timestamp_dt = datetime.datetime.fromisoformat(timestamp)
        # if timestamp contains TZ info, timestamp_dt is datetime aware
        # if timestamp doesn't contain any TZ info, timestamp_dt is datetime naive
        #   in this case, we read the TZ from timestamp_tz (if it is false, we consider
        #   it is the TZ configured on account.statement.import.api)
        if not timestamp_dt.tzinfo:
            if timestamp_tz:
                timestamp_dt = timestamp_tz.localize(timestamp_dt)
            else:
                timestamp_dt = speedy["tz"].localize(timestamp_dt)
        return timestamp_dt

    def _api_import_timestamp_iso8601_to_datetime(
        self, timestamp, speedy, timestamp_tz=False
    ):
        timestamp_dt = self._api_import_timestamp_iso8601_to_datetime_aware(
            timestamp, speedy, timestamp_tz=timestamp_tz
        )
        if not timestamp_dt:
            return False
        # switch to UTC
        timestamp_dt_utc = timestamp_dt.astimezone(pytz.utc)
        timestamp_dt_naive = timestamp_dt_utc.replace(tzinfo=None)
        return timestamp_dt_naive

    def _api_import_timestamp_iso8601_to_date(
        self, timestamp, speedy, timestamp_tz=False
    ):
        timestamp_dt = self._api_import_timestamp_iso8601_to_datetime_aware(
            timestamp, speedy, timestamp_tz=timestamp_tz
        )
        if not timestamp_dt:
            return False
        # switch to our TZ and convert to date
        timestamp_dt_our_tz = timestamp_dt.astimezone(speedy["tz"])
        date_dt = timestamp_dt_our_tz.date()
        return date_dt
