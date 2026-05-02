# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Account Statement Import API",
    "version": "18.0.3.0.0",
    "category": "Accounting",
    "license": "AGPL-3",
    "summary": "Base module to download bank statement via an API",
    "author": "Akretion",
    "maintainers": ["alexis-via"],
    "website": "https://github.com/akretion/bank-statement-import-api",
    "depends": ["account_statement_import_base"],
    "data": [
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "wizards/account_statement_import_api_generate_url_view.xml",
        "wizards/account_statement_import_api_create_user_view.xml",
        "wizards/account_statement_import_api_delete_user_view.xml",
        "wizards/account_statement_import_api_delete_connector_view.xml",
        "views/account_statement_import_api_log.xml",
        "views/account_statement_import_api_account.xml",
        "views/account_statement_import_api_connector_status.xml",
        "views/account_statement_import_api_connector.xml",
        "views/account_journal.xml",
        "views/account_statement_import_api.xml",
    ],
    "installable": True,
}
