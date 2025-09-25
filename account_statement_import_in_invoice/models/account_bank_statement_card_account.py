# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountBankStatementCardAccount(models.Model):
    _name = "account.bank.statement.card.account"
    _description = "Card-specific Accounts"
    _check_company_auto = True

    categ_id = fields.Many2one(
        "account.bank.statement.expense.categ", ondelete="cascade", required=True
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    card_id = fields.Many2one(
        "account.bank.statement.card",
        ondelete="cascade",
        domain="[('company_id', '=', company_id)]",
        check_company=True,
        required=True,
    )
    account_id = fields.Many2one(
        "account.account",
        domain="[('company_id', '=', company_id), ('deprecated', '=', False)]",
        check_company=True,
        required=True,
    )

    _sql_constraints = [
        (
            "categ_card_uniq",
            "unique(categ_id, card_id)",
            "This card has already been configured on this expense category.",
        )
    ]
