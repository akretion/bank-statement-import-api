# Copyright 2026 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import Command, _, api, fields, models

logger = logging.getLogger(__name__)

DAYS_BEFORE_EXPIRY_WARN = 10


class AccountStatementImportApiConnector(models.Model):
    _name = "account.statement.import.api.connector"
    _description = "Bank statement import API Connector"
    _order = "statement_import_api_id, name"

    statement_import_api_id = fields.Many2one(
        "account.statement.import.api",
        ondelete="cascade",
        string="Statement Import API",
        required=True,
    )
    company_id = fields.Many2one(
        related="statement_import_api_id.company_id", store=True
    )
    name = fields.Char(required=True)
    auth_expiry_date = fields.Date(readonly=True, string="Auth Expiry")
    auth_expiry_warn_type = fields.Selection(
        [
            ("warning", "Warning"),
            ("danger", "Danger"),
        ],
        compute="_compute_auth_expiry_warn_type",
    )
    sync_status = fields.Selection("_selection_sync_status", readonly=True)
    sync_status_message = fields.Text(readonly=True, string="Sync Message")
    sync_status_ids = fields.One2many(
        "account.statement.import.api.connector.status",
        "connector_id",
        string="Status History",
        readonly=True,
    )
    last_sync_datetime = fields.Datetime(
        readonly=True,
        help="Last sync between the bank aggragator and the bank "
        "as reported by the bank aggregator. This is not the last sync "
        "between Odoo and the bank aggregator.",
    )
    identifier = fields.Char(readonly=True, required=True)
    api_account_ids = fields.One2many(
        "account.statement.import.api.account",
        "connector_id",
        string="API Bank Accounts",
        readonly=True,
    )

    _sql_constraints = [
        (
            "statement_import_api_identifier_unique",
            "unique(statement_import_api_id, identifier)",
            "This identifier is already used by another connector "
            "of the same statement import API.",
        ),
        # no unicity on (statement_import_api_id, name) because
        # the connector is created by code and we don't want to block that
    ]

    @api.model
    def _selection_sync_status(self):
        """Also used in account.statement.import.api.connector.status"""
        return [
            ("ok", _("OK")),
            ("warning", _("Warning")),
            ("ko", _("Not Working")),
        ]

    def _compute_auth_expiry_warn_type(self):
        config_key = "account_statement_import_api.days_before_expiry_warn"
        warn_limit_days_str = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(config_key, default=str(DAYS_BEFORE_EXPIRY_WARN))
        )
        try:
            warn_limit_days = int(warn_limit_days_str)
        except Exception:
            warn_limit_days = DAYS_BEFORE_EXPIRY_WARN
            logger.warning(
                f"Failed to convert ir.config_parameter {config_key} "
                f"({warn_limit_days_str}) to integer. "
                f"Using default value {warn_limit_days} days"
            )
        if warn_limit_days < 0:
            warn_limit_days = DAYS_BEFORE_EXPIRY_WARN
        today = fields.Date.context_today(self)
        for connector in self:
            warn_type = False
            if connector.auth_expiry_date:
                days = (connector.auth_expiry_date - today).days
                if days <= 0:
                    warn_type = "danger"
                elif days <= warn_limit_days:
                    warn_type = "warning"
            connector.auth_expiry_warn_type = warn_type

    def name_get(self):
        res = []
        status2label = dict(
            self.fields_get("sync_status", "selection")["sync_status"]["selection"]
        )
        today = fields.Date.context_today(self)
        for rec in self:
            dname = rec.name
            if rec.sync_status:
                dname = f"{dname} [{status2label[rec.sync_status]}]"
            if rec.auth_expiry_date:
                delay = (rec.auth_expiry_date - today).days
                expire_str = False
                if delay < 0:
                    expire_str = _("⚠ Expired")
                elif delay == 0:
                    expire_str = _("⚠ Expire today")
                elif delay < 15:
                    expire_str = _("⚠ Expire in %d days", delay)
                if expire_str:
                    dname = " ".join([dname, expire_str])
            res.append((rec.id, dname))
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("sync_status"):
                vals["sync_status_ids"] = [
                    Command.create(
                        {
                            "sync_status": vals["sync_status"],
                            "sync_status_message": vals.get("sync_status_message"),
                        }
                    )
                ]
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("sync_status"):
            history_obj = self.env["account.statement.import.api.connector.status"]
            for connector in self:
                if connector.sync_status != vals["sync_status"] or (
                    (connector.sync_status_message or vals.get("sync_status_message"))
                    and connector.sync_status_message != vals.get("sync_status_message")
                ):
                    history_obj.create(
                        {
                            "connector_id": connector.id,
                            "sync_status": vals["sync_status"],
                            "sync_status_message": vals.get("sync_status_message"),
                        }
                    )
        return super().write(vals)
