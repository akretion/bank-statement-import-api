# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Account Statement Import In Invoice",
    "version": "16.0.1.0.0",
    "category": "Accounting",
    "license": "AGPL-3",
    "summary": "Enrich bank statement lines to allow the creation of vendor bills",
    "author": "Akretion",
    "maintainers": ["alexis-via"],
    "website": "https://github.com/akretion/bank-statement-import-api",
    "depends": ["account_statement_import_base", "account_reconcile_oca"],
    "data": [
        "security/ir.model.access.csv",
        "views/account_bank_statement_expense_categ.xml",
        "views/account_bank_statement_card.xml",
        "views/account_bank_statement_line.xml",
        "views/ir_attachment.xml",
        "wizards/res_config_settings_view.xml",
    ],
    "installable": True,
}
