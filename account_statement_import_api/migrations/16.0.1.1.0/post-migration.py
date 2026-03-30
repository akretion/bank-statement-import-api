# Copyright 2026 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    connectors = env["account.statement.import.api.connector"].search(
        [("company_id", "=", False)]
    )
    for connector in connectors:
        if connector.api_account_ids:
            if connector.api_account_ids[0].company_id:
                connector.write(
                    {"company_id": connector.api_account_ids[0].company_id.id}
                )
        else:
            connector.unlink()
