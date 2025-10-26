# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountStatementImportApiAccount(models.Model):
    _name = "account.statement.import.api.account"
    _description = "Bank statement import API Account"
    _order = "statement_import_api_id, bank_name, currency_id, name, account_number"

    statement_import_api_id = fields.Many2one(
        "account.statement.import.api",
        ondelete="cascade",
        string="Statement Import API",
    )
    service = fields.Selection(related="statement_import_api_id.service", store=True)
    identifier = fields.Char(
        required=True,
        readonly=True,
        help="Technical ID given by the bank statement import provider for this bank account.",
    )
    name = fields.Char(required=True, string="Label")
    account_number = fields.Char(readonly=True)
    bank_name = fields.Char(string="Bank", readonly=True)
    account_type = fields.Char()
    currency_id = fields.Many2one("res.currency", readonly=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", readonly=True, index=True)
    auth_expiry_date = fields.Date(readonly=True, string="Auth Expiry")

    _sql_constraints = [
        (
            "statement_import_api_identifier_unique",
            "unique(statement_import_api_id, identifier)",
            "This identifier already exists for this statement import API.",
        )
    ]

    def name_get(self):
        res = []
        for rec in self:
            name = rec.name
            if rec.bank_name and rec.account_number:
                name = f"{name} - {rec.account_number} {rec.bank_name}"
            elif rec.bank_name:
                name = f"{name} {rec.bank_name}"
            elif rec.account_number:
                name = f"{name} - {rec.account_number}"
            if rec.currency_id:
                name = f"{name} ({rec.currency_id.name})"
            res.append((rec.id, name))
        return res
