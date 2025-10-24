# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountStatementImportApiCompanyUser(models.Model):
    _inherit = "account.statement.import.api.company.user"

    powens_token = fields.Char(readonly=False, groups="base.group_system")
