# Copyright 2026 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models


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
    company_id = fields.Many2one("res.company", required=True, ondelete="cascade")
    name = fields.Char(required=True)
    auth_expiry_date = fields.Date(readonly=True, string="Auth Expiry")
    auth_expiry_warn_type = fields.Selection(
        [
            ("warning", "Warning"),
            ("danger", "Danger"),
        ],
        compute="_compute_auth_expiry_warn_type",
    )
    sync_status = fields.Selection(
        [
            ("ok", "OK"),
            ("warning", "Warning"),
            ("ko", "Not Working"),
        ],
        readonly=True,
    )
    sync_status_message = fields.Text(readonly=True, string="Sync Message")
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
            "This identifier already exists for this statement import API.",
        ),
        # no unicity on (statement_import_api_id, name) because
        # the connector is created by code and we don't want to block that
    ]

    def _compute_auth_expiry_warn_type(self):
        today = fields.Date.context_today(self)
        for connector in self:
            warn_type = False
            if connector.auth_expiry_date:
                days = (connector.auth_expiry_date - today).days
                if days <= 0:
                    warn_type = "danger"
                elif days <= 10:
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
