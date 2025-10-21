# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountStatementImportApiSetIdentifier(models.TransientModel):
    _name = "account.statement.import.api.set.identifier"
    _description = "Set identifier on bank journal for bank statement import via API"

    journal_id = fields.Many2one(
        "account.journal", required=True, readonly=True, string="Bank Journal"
    )
    bank_account_id = fields.Many2one(related="journal_id.bank_account_id")
    line_id = fields.Many2one(
        "account.statement.import.api.set.identifier.line",
        domain="[('wizard_id', '=', id)]",
        string="Selected Account",
    )
    line_ids = fields.One2many(
        "account.statement.import.api.set.identifier.line",
        "wizard_id",
        string="Available Accounts",
        readonly=True,
    )

    def validate(self):
        self.ensure_one()
        if not self.line_id:
            raise UserError(_("You must select an account."))
        self.journal_id.write(
            {"statement_import_api_identifier": self.line_id.identifier}
        )


class AccountStatementImportApiSetIdentifierLine(models.TransientModel):
    _name = "account.statement.import.api.set.identifier.line"
    _description = (
        "Choices to set identifier on bank journal for bank statement import via API"
    )

    wizard_id = fields.Many2one(
        "account.statement.import.api.set.identifier", ondelete="cascade", required=True
    )
    identifier = fields.Char(required=True)
    name = fields.Char(required=True, string="Label")
    account_number = fields.Char()
    bank_name = fields.Char(string="Bank")
    account_type = fields.Char()

    def name_get(self):
        res = []
        for rec in self:
            name = rec.name
            if rec.bank_name:
                name = f"{name} - {rec.bank_name}"
            res.append((rec.id, name))
        return res
