# Copyright 2026 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.misc import format_date


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    in_invoice_start_date = fields.Date(string="Start Date")
    in_invoice_end_date = fields.Date(string="End Date")

    @api.constrains("in_invoice_start_date", "in_invoice_end_date")
    def _check_in_invoice_start_end_dates(self):
        for line in self:
            if line.in_invoice_start_date and not line.in_invoice_end_date:
                raise ValidationError(
                    _(
                        "Missing End Date on bank statement line '%s'.",
                        line.display_name,
                    )
                )
            if line.in_invoice_end_date and not line.in_invoice_start_date:
                raise ValidationError(
                    _(
                        "Missing Start Date on bank statement line '%s'.",
                        line.display_name,
                    )
                )
            if (
                line.in_invoice_end_date
                and line.in_invoice_start_date
                and line.in_invoice_start_date > line.in_invoice_end_date
            ):
                raise ValidationError(
                    _(
                        "Start Date (%(start)s) should be before or be the same as "
                        "End Date (%(end)s) on bank statement line '%(line)s'.",
                        line=line.display_name,
                        start=format_date(self.env, line.in_invoice_start_date),
                        end=format_date(self.env, line.in_invoice_end_date),
                    )
                )

    def _prepare_in_invoice(self):
        vals = super()._prepare_in_invoice()
        if (
            self.in_invoice_start_date
            and self.in_invoice_end_date
            and self.in_invoice_end_date >= self.in_invoice_start_date
        ):
            vals["invoice_line_ids"][0][2].update(
                {
                    "start_date": self.in_invoice_start_date,
                    "end_date": self.in_invoice_end_date,
                }
            )
        return vals
