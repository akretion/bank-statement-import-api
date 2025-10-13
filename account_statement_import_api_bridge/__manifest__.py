# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Account Statement Import API Bridge",
    "version": "16.0.1.0.0",
    "category": "Accounting",
    "license": "AGPL-3",
    "summary": "Use BridgeAPI.io to download bank statement lines",
    "author": "Akretion",
    "maintainers": ["alexis-via"],
    "website": "https://github.com/akretion/bank-statement-import-api",
    "depends": ["account_statement_import_api"],
    "data": [
        "security/ir.model.access.csv",
        "views/account_statement_import_api.xml",
        "views/account_journal.xml",
        "views/res_company.xml",
        "wizards/bridge_match_account_view.xml",
    ],
    "installable": True,
}
