# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Account Statement Import API Bridge",
    "version": "18.0.2.0.0",
    "category": "Accounting",
    "license": "AGPL-3",
    "summary": "Use BridgeAPI.io to download bank statement lines",
    "author": "Akretion",
    "maintainers": ["alexis-via"],
    "website": "https://github.com/akretion/bank-statement-import-api",
    "depends": ["account_statement_import_api"],
    "external_dependencies": {"python": ["unidecode"]},
    "data": [
        "data/ir_cron.xml",
        "views/account_journal.xml",
        "views/account_statement_import_api.xml",
        "wizards/account_statement_import_api_create_user_view.xml",
    ],
    "installable": True,
}
