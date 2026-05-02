# Copyright 2026 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Account Statement Import In Invoice Start End Dates",
    "version": "16.0.1.0.0",
    "category": "Accounting",
    "license": "AGPL-3",
    "summary": "Glue module between account_statement_import_in_invoice "
    "and account_invoice_start_end_dates",
    "author": "Akretion",
    "maintainers": ["alexis-via"],
    "website": "https://github.com/akretion/bank-statement-import-api",
    "depends": [
        "account_statement_import_in_invoice",
        "account_invoice_start_end_dates",
    ],
    "data": [
        "views/account_bank_statement_line.xml",
    ],
    "installable": True,
}
