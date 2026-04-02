# Copyright 2026 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    bank_statement_card_ids = fields.One2many(
        "account.bank.statement.card", "journal_id", string="Payment Cards"
    )
    bank_statement_card_count = fields.Integer(
        compute="_compute_bank_statement_card_count", string="Number of Payment Cards"
    )

    def _compute_bank_statement_card_count(self):
        rg_res = self.env["account.bank.statement.card"].read_group(
            [("journal_id", "in", self.ids)], ["journal_id"], ["journal_id"]
        )
        mapped_data = {x["journal_id"][0]: x["journal_id_count"] for x in rg_res}
        for journal in self:
            journal.bank_statement_card_count = mapped_data.get(journal.id, 0)
