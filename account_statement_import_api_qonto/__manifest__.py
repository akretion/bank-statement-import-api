# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Account Statement Import API Qonto",
    "version": "16.0.1.0.0",
    "category": "Accounting",
    "license": "AGPL-3",
    "summary": "Use the Qonto API to download bank statement lines",
    "author": "Akretion",
    "maintainers": ["alexis-via"],
    "website": "https://github.com/akretion/bank-statement-import-api",
    "depends": ["account_statement_import_in_invoice_api"],
    "data": [
        "data/ir_cron.xml",
        "data/account_bank_statement_expense_categ.xml",
    ],
    "post_init_hook": "update_bank_statement_expense_categ",
    "installable": True,
}
