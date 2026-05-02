# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountBankStatementExpenseCateg(models.Model):
    _name = "account.bank.statement.expense.categ"
    _description = "Bank Statement Expense Category"
    _order = "service, name"

    code = fields.Char(required=True)
    name = fields.Char(required=True, translate=True, string="Label")
    service = fields.Selection(
        [
            ("test", "Test"),
        ],
        required=True,
        index=True,
    )
    account_id = fields.Many2one(
        "account.account",
        string="Account",
        company_dependent=True,
        domain="[('deprecated', '=', False)]",
    )
    active = fields.Boolean(default=True)
    card_account_ids = fields.One2many(
        "account.bank.statement.card.account",
        "categ_id",
        string="Card-specific Accounts",
    )

    _sql_constraints = [
        (
            "code_service_uniq",
            "unique(code, service)",
            "This code already exists for this service.",
        )
    ]
