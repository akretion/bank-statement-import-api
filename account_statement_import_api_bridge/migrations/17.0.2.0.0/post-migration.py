# Copyright 2026 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from openupgradelib import openupgrade

logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    company_id2user_idents = {}
    env.cr.execute(
        """
        SELECT company_id, identifier, bridge_external_identifier
        FROM account_statement_import_api_company_user
        WHERE service='bridge' and company_id IS NOT NULL
        """
    )
    for company_user in env.cr.fetchall():
        company_id2user_idents[company_user[0]] = {
            "user_identifier": company_user[1],
            "bridge_external_user_identifier": company_user[2],
        }
    import_apis = env["account.statement.import.api"].search(
        [("service", "=", "bridge")]
    )
    # for some strange reasons that I don't explain
    # odoo will have already put a default value for company_id on account.statement.import.api
    company_id2import_api_id = {}
    for import_api in import_apis:
        if import_api.company_id:
            company_id2import_api_id[import_api.company_id.id] = import_api.id
            import_api.write(company_id2user_idents[import_api.company_id.id])
            logger.info(
                "Writing user identifier on bank statement import API ID %d",
                import_api.id,
            )
        for api_account in import_api.api_account_ids:
            if api_account.company_id:
                company_id = api_account.company_id.id
                if not company_id2import_api_id:
                    # will not happend because of the strange behavior described above
                    import_api.write({"company_id": company_id})
                    logger.info(
                        "Writing company ID %s on bank statement import API %s ID %d",
                        company_id,
                        import_api.display_name,
                        import_api.id,
                    )
                    api_account.connector_id.write({"company_id": company_id})
                    company_id2import_api_id[company_id] = import_api.id
                elif company_id not in company_id2import_api_id:
                    import_api_vals = {
                        "name": f"{import_api.service} MIGRATION",
                        "company_id": company_id,
                        "service": "bridge",
                        "tz": import_api.tz,
                    }
                    import_api_vals.update(company_id2user_idents[company_id])
                    new_import_api = env["account.statement.import.api"].create(
                        import_api_vals
                    )
                    logger.info(
                        "Created a new bank statement import API ID %d "
                        "in company ID %d",
                        new_import_api.id,
                        company_id,
                    )
                    company_id2import_api_id[company_id] = new_import_api.id
                if company_id in company_id2import_api_id:
                    new_import_api_id = company_id2import_api_id[company_id]
                    if api_account.statement_import_api_id.id != new_import_api_id:
                        logger.info(
                            "Changing API account %s ID %d from BS import API %d to %d",
                            api_account.display_name,
                            api_account.id,
                            api_account.statement_import_api_id.id,
                            new_import_api_id,
                        )
                        api_account.write(
                            {"statement_import_api_id": new_import_api_id}
                        )
                        api_account.connector_id.write(
                            {"statement_import_api_id": new_import_api_id}
                        )
                        if api_account.journal_ids:
                            api_account.journal_ids.write(
                                {"statement_import_api_id": new_import_api_id}
                            )
            else:
                logger.warning(
                    "No company on API account %s ID %d. Will required a manual data mig",
                    api_account.display_name,
                    api_account.id,
                )
