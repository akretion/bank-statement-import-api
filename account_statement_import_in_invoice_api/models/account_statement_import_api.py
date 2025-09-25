# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import models

logger = logging.getLogger(__name__)


class AccountStatementImportApi(models.Model):
    _inherit = "account.statement.import.api"

    def _prepare_speedy(self):
        speedy = super()._prepare_speedy()
        exp_categ_read = (
            self.env["account.bank.statement.expense.categ"]
            .with_context(active_test=False)
            .search_read([("service", "=", self.service)], ["code"])
        )
        expcateg_code2id = {x["code"]: x["id"] for x in exp_categ_read}
        speedy["expcateg_code2id"] = expcateg_code2id
        return speedy
