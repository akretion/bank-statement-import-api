# Copyright 2026 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from datetime import timedelta

from odoo import api, fields, models

logger = logging.getLogger(__name__)
DEFAULT_STATUS_HISTORY_VACUUM_DAYS = 1098


class AccountStatementImportApiConnectorStatus(models.Model):
    _name = "account.statement.import.api.connector.status"
    _description = "History for Bank statement import API Connector Status"
    _order = "id desc"

    connector_id = fields.Many2one(
        "account.statement.import.api.connector",
        ondelete="cascade",
        required=True,
        readonly=True,
    )
    statement_import_api_id = fields.Many2one(
        "account.statement.import.api",
        related="connector_id.statement_import_api_id", store=True,
    )
    company_id = fields.Many2one(
        related="connector_id.statement_import_api_id.company_id", store=True
    )
    sync_status = fields.Selection(
        "_selection_sync_status",
        readonly=True,
        required=True,
    )
    sync_status_message = fields.Text(readonly=True, string="Sync Message")

    @api.model
    def _selection_sync_status(self):
        conn_obj = self.env["account.statement.import.api.connector"]
        return conn_obj._selection_sync_status()

    @api.autovacuum
    def _gc_old_logs(self):
        config_key = "account_statement_import_api.status_history_days"
        days_str = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(config_key, default=str(DEFAULT_STATUS_HISTORY_VACUUM_DAYS))
        )
        try:
            days = int(days_str)
        except Exception:
            days = DEFAULT_STATUS_HISTORY_VACUUM_DAYS
            logger.warning(
                f"Failed to convert ir.config_parameter {config_key} ({days_str}) "
                f"to integer. Using default value {days} days"
            )
        limit_date = fields.Datetime.now() - timedelta(days)
        logger.info(
            f"Autovacuum of bank statement import API status history older than {days} days"
        )
        self.search([("create_date", "<", limit_date)]).unlink()
