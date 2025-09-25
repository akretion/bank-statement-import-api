# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from datetime import timedelta

from odoo import api, fields, models


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
    journal_id = fields.Many2one(
        "account.journal",
        string="Bank Journal",
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company", related="journal_id.company_id", store=True
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
        """Method automatically called by the autovaccum internal data cron"""
        days_str = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("account_statement_import_api.log_days", default="180")
        )
        days = int(days_str)
        limit_date = fields.Datetime.now() - timedelta(days)
        self.search([("create_date", "<", limit_date)]).unlink()
