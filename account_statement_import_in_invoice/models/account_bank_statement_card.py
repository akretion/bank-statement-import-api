# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class AccountBankStatementCard(models.Model):
    _name = "account.bank.statement.card"
    _description = "Payment Card"
    _check_company_auto = True

    code = fields.Char(
        required=True, help="Code used in the Bank API for that payment card."
    )
    name = fields.Char(string="Label")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Bank Journal",
        check_company=True,
        required=True,
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
        ondelete="restrict",
    )
    misc_partner_id = fields.Many2one(
        "res.partner",
        help="Misc partner used when the bank statement line is linked to this card. "
        "Otherwise, Odoo will use the misc partner configured on the "
        "accounting configuration page.",
    )

    @api.depends("name", "code")
    def _compute_display_name(self):
        for card in self:
            card.display_name = card.name or card.code

    _sql_constraints = [
        (
            "code_journal_unique",
            "unique(code, journal_id)",
            "A card already exists in this journal with the same code.",
        ),
        (
            "name_company_unique",
            "unique(name, company_id)",
            "This label is already used on another card in this company.",
        ),
    ]
