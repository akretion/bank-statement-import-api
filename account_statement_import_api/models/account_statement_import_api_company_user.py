# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountStatementImportApiCompanyUser(models.Model):
    _name = "account.statement.import.api.company.user"
    _description = "Per-Company Users for Bank Statement Import via API"

    statement_import_api_id = fields.Many2one(
        "account.statement.import.api",
        ondelete="cascade",
        string="Statement Import API",
        required=True,
    )
    identifier = fields.Char(required=True)
    company_id = fields.Many2one(
        "res.company", index=True, required=True, default=lambda self: self.env.company
    )
    service = fields.Selection(related="statement_import_api_id.service", store=True)

    _sql_constraints = [
        (
            "company_import_api_unique",
            "unique(statement_import_api_id, company_id)",
            "This bank statement import API already has a user identifier for this company.",
        ),
        (
            "identifier_import_api_unique",
            "unique(statement_import_api_id, identifier)",
            "This user identifier is already used on this bank statement import API.",
        ),
    ]

    def name_get(self):
        res = []
        for rec in self:
            dname = f"{rec.identifier} ({rec.company_id.name})"
            res.append((rec.id, dname))
        return res
