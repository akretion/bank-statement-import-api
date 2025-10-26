# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountStatementImportApiAccount(models.Model):
    _inherit = "account.statement.import.api.account"

    powens_connection_identifier = fields.Integer(readonly=True, string="Connection ID")
