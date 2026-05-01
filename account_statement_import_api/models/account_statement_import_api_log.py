# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from datetime import timedelta

from odoo import _, api, fields, models

logger = logging.getLogger(__name__)
DEFAULT_LOG_VACUUM_DAYS = 600


class AccountStatementImportApiLog(models.Model):
    _name = "account.statement.import.api.log"
    _description = "Logs for the download of bank statements via API"
    _order = "id desc"
    _rec_name = "create_date"

    statement_import_api_id = fields.Many2one(
        "account.statement.import.api",
        string="Statement Import API",
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    type = fields.Selection(
        [
            ("statement_line", "Bank Statement Line Update"),
            ("other", "Get Balances and Update Connectors"),
        ],
        readonly=True,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Bank Journal",
        readonly=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="statement_import_api_id.company_id", store=True
    )
    logs = fields.Html(readonly=True)
    status = fields.Selection(
        [
            ("success", "Success"),
            ("success_warn", "Success with Warnings"),
            ("failure", "Failure"),
        ],
        readonly=True,
        required=True,
    )
    new_line_count = fields.Integer(
        string="Number of New Statement Lines", readonly=True
    )
    updated_line_count = fields.Integer(
        string="Number of Statement Lines Updated", readonly=True
    )

    @api.autovacuum
    def _gc_old_logs(self):
        """Method automatically called by the autovacuum internal data cron"""
        config_key = "account_statement_import_api.log_days"
        days_str = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(config_key, default=str(DEFAULT_LOG_VACUUM_DAYS))
        )
        try:
            days = int(days_str)
        except Exception:
            days = DEFAULT_LOG_VACUUM_DAYS
            logger.warning(
                f"Failed to convert ir.config_parameter {config_key} ({days_str}) "
                f"to integer. Using default value {days} days"
            )
        limit_date = fields.Datetime.now() - timedelta(days)
        logger.info(
            f"Autovacuum of bank statement import API logs older than {days} days"
        )
        self.search([("create_date", "<", limit_date)]).unlink()

    def _prepare_notification_action(self):
        """This method can apply on several logs"""
        if not self:
            return {}
        fail_log = warn_log = False
        for log in self:
            if log.status == "failure":
                fail_log = log
            elif log.status == "success_warn":
                warn_log = log
        if fail_log:
            title = _("Sync failed on %s", fail_log.journal_id.display_name)
            message = _(
                "See failure log on Statement Import API '%s'.",
                fail_log.statement_import_api_id.display_name,
            )
            ptype = "danger"
        else:
            title = _("Successful Sync")
            if warn_log:
                ptype = "warning"
                message = _(
                    "Sync with warning(s), cf warning log on Statement Import API '%s'.",
                    warn_log.statement_import_api_id.display_name,
                )
            else:
                new_line_count = sum([log.new_line_count for log in self])
                updated_line_count = sum([log.updated_line_count for log in self])
                ptype = "success"
                if new_line_count > 1:
                    message = _("%s bank statement lines created.", new_line_count)
                elif new_line_count == 1:
                    message = _("1 bank statement line created.")
                else:
                    message = _("No new bank statement lines.")
                if updated_line_count:
                    message += " " + _("%s updated.", updated_line_count)

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

    @api.model
    def _prepare_log(self, log_type, result, speedy, journal_id=None):
        assert log_type in ("other", "statement_line")
        if log_type == "statement_line":
            assert journal_id
        logs = []
        has_error = False
        has_warning = False
        for log_level, msg in result["logs"]:
            if log_level == "info":
                logs.append(
                    f'<span style="color: green; font-weight: bold">'
                    f"INFO </span>{msg}"
                )
            elif log_level == "warning":
                logs.append(
                    f'<span style="color: orange; font-weight: bold">'
                    f"WARNING </span>{msg}"
                )
                has_warning = True
            elif log_level == "error":
                logs.append(
                    f'<span style="color: red; font-weight: bold">'
                    f"ERROR </span>{msg}"
                )
                has_error = True
            elif log_level == "debug":
                logs.append(
                    f'<span style="color: darkblue; font-weight: bold">'
                    f"DEBUG </span>{msg}"
                )
            else:  # Should not happen
                logs.append(msg)
        if has_error:
            status = "failure"
        else:
            if has_warning:
                status = "success_warn"
            else:
                status = "success"
        log_vals = {
            "journal_id": journal_id,
            "type": log_type,
            "statement_import_api_id": speedy["statement_import_api_id"],
            "status": status,
            "new_line_count": result.get("new_line_count"),
            "updated_line_count": result.get("updated_line_count"),
            "logs": "<br>".join(logs),
        }
        return log_vals

    @api.model
    def _create_log(self, log_type, result, speedy, journal_id=None):
        if not result["logs"]:
            logger.debug("Empty logs: no bank statement import API log created")
            return None
        vals = self._prepare_log(log_type, result, speedy, journal_id=journal_id)
        log = self.sudo().create(vals)
        logger.debug(
            "Bank statement import API log created type %s ID %d", log_type, log.id
        )
        return log

    @api.model
    def _debug_log(self, result, msg):
        logger.debug(msg)
        result["logs"].append(("debug", msg))

    @api.model
    def _info_log(self, result, msg):
        logger.info(msg)
        result["logs"].append(("info", msg))

    @api.model
    def _warning_log(self, result, msg):
        logger.warning(msg)
        result["logs"].append(("warning", msg))

    @api.model
    def _error_log(self, result, msg):
        logger.error(msg)
        result["logs"].append(("error", msg))
