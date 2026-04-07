# Copyright 2026 Akretion France (https://www.akretion.com/)
# @author: Benoit Guillot <benoit.guillot@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountBankStatementAnalyticAccount(models.Model):
    _name = "account.bank.statement.analytic.account"
    _description = "Bank Statement Analytic Account"
    _order = "service, parent_name, name"

    statement_import_api_id = fields.Many2one(
        "account.statement.import.api",
        ondelete="cascade",
        string="Statement Import API",
        required=True,
    )
    identifier = fields.Char(
        required=True,
        readonly=True,
        help="Technical ID given by the bank statement import provider for this "
        "analytic account.",
    )
    name = fields.Char(required=True, string="Label")
    service = fields.Selection(related="statement_import_api_id.service", store=True)
    parent_name = fields.Char(required=True, index=True, string="Parent Label")
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        domain="[('company_id', 'in', [False, company_id])]",
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        related="statement_import_api_id.company_id", store=True
    )

    _sql_constraints = [
        (
            "identifier_statement_import_api_uniq",
            "unique(identifier, statement_import_api_id)",
            "This identifier is already used on another bank statement "
            "analytic account for this statement import API.",
        )
    ]

    def name_get(self):
        res = []
        for rec in self:
            name = rec.name
            if rec.parent_name:
                name = f"[{rec.parent_name}] {name}"
            res.append((rec.id, name))
        return res
