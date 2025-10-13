# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import UserError


class BridgeMatchAccount(models.TransientModel):
    _name = "bridge.match.account"
    _description = "Match Bridge Account to Odoo Bank Journal"

    journal_id = fields.Many2one(
        "account.journal", required=True, readonly=True, string="Bank Journal"
    )
    option_id = fields.Many2one(
        "bridge.match.account.option",
        domain="[('wizard_id', '=', id)]",
        string="Bridge Account",
    )
    option_ids = fields.One2many(
        "bridge.match.account.option",
        "wizard_id",
        string="Available Bridge Accounts",
        readonly=True,
    )

    def run(self):
        self.ensure_one()
        if not self.option_id:
            raise UserError(_("You must select a bridge account."))
        self.journal_id.write(
            {"bridge_account_identifier": self.option_id.bridge_identifier}
        )


class BridgeMatchAccountOption(models.TransientModel):
    _name = "bridge.match.account.option"
    _description = "Choice for Match Bridge Account Wizard"

    wizard_id = fields.Many2one(
        "bridge.match.account", ondelete="cascade", required=True
    )
    bridge_identifier = fields.Integer(required=True)
    name = fields.Char(required=True, string="Label")
    iban = fields.Char(string="IBAN")
    bridge_provider_name = fields.Char(string="Bank")
    account_type = fields.Char()

    def name_get(self):
        res = []
        for rec in self:
            name = rec.name
            if rec.bridge_provider_name:
                name = f"{name} - {rec.bridge_provider_name}"
            res.append((rec.id, name))
        return res
