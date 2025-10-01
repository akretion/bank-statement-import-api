# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AccountBankStatementExpenseCateg(models.Model):
    _inherit = "account.bank.statement.expense.categ"

    service = fields.Selection(
        selection_add=[("qonto", "Qonto")], ondelete={"qonto": "cascade"}
    )

    def _qonto_account_mapping(self):
        mapping = {
            "FR": {
                "restaurant_and_bar": "6256",
                "food_and_grocery": "6256",
                "transport": "6251",
                "gas_station": "6251",
                "hotel_and_lodging": "6251",
                "it_and_electronics": "6063",
                "hardware_and_equipment": "6063",
                "office_supply": "6064",
                "office_rental": "6132",
                "utility": "6061",
                "insurance": "616",
                "logistics": "624",
                "online_service": "626",
                "legal_and_accounting": "6226",
                "finance": "6278",
                "salary": "6411",
                "marketing": "6231",
                "manufacturing": "601",
                # Too generic
                # 'other_service': '',
                # 'other_expense': '',
                "fees": "6226",  # honoraires
                "subscription": "6181",
                "qonto_fee": "6278",
            }
        }
        return mapping
