# Copyright 2026 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.logged_query(
        env.cr,
        """
            UPDATE account_statement_import_api_log SET type='statement_line'
            WHERE journal_id IS NOT null
            """,
    )
    openupgrade.logged_query(
        env.cr,
        """
            UPDATE account_statement_import_api_log SET type='other'
            WHERE journal_id IS null
            """,
    )
