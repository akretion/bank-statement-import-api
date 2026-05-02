# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Account Statement Import In Invoice API",
    "version": "18.0.1.0.0",
    "category": "Accounting",
    "license": "AGPL-3",
    "summary": "Glue module between account_statement_import_in_invoice "
    "and account_statement_import_api",
    "author": "Akretion",
    "maintainers": ["alexis-via"],
    "website": "https://github.com/akretion/bank-statement-import-api",
    "depends": ["account_statement_import_api", "account_statement_import_in_invoice"],
    "external_dependencies": {"python": ["unidecode"]},
    "data": [
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "views/account_bank_statement_analytic_account.xml",
        "views/account_bank_statement_line.xml",
        "views/account_statement_import_api.xml",
    ],
    "installable": True,
    "auto_install": True,
}
