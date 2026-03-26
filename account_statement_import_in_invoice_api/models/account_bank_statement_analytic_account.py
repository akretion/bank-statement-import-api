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
    parent_name = fields.Char(required=True, index=True, string="Parent label")
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Account analytic",
        domain="[('company_id', 'in', [False, company_id])]",
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(comodel_name="res.company", required=True)

    _sql_constraints = [
        (
            "identifier_service_company_uniq",
            "unique(identifier, service, company)",
            "This identifier already exists for this service and this company.",
        )
    ]
