# Copyright 2026 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute(
        "SELECT cron_id from account_statement_import_api WHERE cron_id IS NOT NULL"
    )
    cron_ids_to_del = tuple([x[0] for x in cr.fetchall()])
    if cron_ids_to_del:
        logger.info(
            "Deleting crons attached to account.statement.import.api IDs %s",
            cron_ids_to_del,
        )
        cr.execute("DELETE FROM ir_cron WHERE id in %s", (cron_ids_to_del,))
