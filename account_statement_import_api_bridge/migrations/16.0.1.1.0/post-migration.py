# Copyright 2026 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

# In post migration script:
# - we can access the registry
# - the new fields are created
# - the old fields are still readable

import logging

from openupgradelib import openupgrade

logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    api_obj = env["account.statement.import.api"]
    bridge_import_apis = api_obj.search([("service", "=", "bridge")])
    for bridge_import_api in bridge_import_apis:
        speedy = bridge_import_api._prepare_speedy()
        result = {"logs": []}
        users_res = api_obj._bridge_get_all_pages(
            "aggregation/users", speedy["bridge_headers_no_token"], result, speedy
        )
        external_user_id2uuid = {}
        for entry in users_res:
            external_user_id2uuid[entry["external_user_id"]] = entry["uuid"]
        for company_user in bridge_import_api.company_user_ids:
            external_user_id = company_user.identifier
            if external_user_id in external_user_id2uuid:
                uuid = external_user_id2uuid[external_user_id]
                company_user.write({"identifier": uuid})
                logger.info(
                    "BridgeAPI user identifier for company %s changed "
                    "from external user ID %s to UUID %s",
                    company_user.company_id.display_name,
                    external_user_id,
                    uuid,
                )
            else:
                logger.warning(
                    "External user identifier %s not found in list of users of %s. "
                    "Maybe it has already been converted to UUID.",
                    company_user.identifier,
                    bridge_import_api.display_name,
                )
