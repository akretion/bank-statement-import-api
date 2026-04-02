# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

logger = logging.getLogger(__name__)

try:
    from unidecode import unidecode
except (ImportError, IOError) as err:
    logger.debug("Cannot import unidecode. Error details below.")
    logger.debug(err)


class AccountStatementImportApiCreateUser(models.TransientModel):
    _inherit = "account.statement.import.api.create.user"

    bridge_external_user_identifier = fields.Char(
        compute="_compute_bridge_external_user_identifier",
        store=True,
        readonly=False,
        precompute=True,
        help="Allowed chars: letters (A to Z, lower and upper case), "
        "digits, dash and underscore.",
        size=128,
    )

    @api.depends("statement_import_api_id")
    def _compute_bridge_external_user_identifier(self):
        for wiz in self:
            bridge_external_user = False
            company = wiz.statement_import_api_id.company_id
            if company:
                company_name = unidecode(company.name).lower().replace(" ", "_")
                bridge_external_user = "".join(
                    re.findall(r"[a-zA-Z0-9_-]+", company_name)
                )[:128]
            wiz.bridge_external_user_identifier = bridge_external_user

    def _bridge_create_user(self, result, speedy):
        ajo = self.env["account.journal"]
        external_user = (
            self.bridge_external_user_identifier
            and self.bridge_external_user_identifier.strip()
        )
        if not external_user:
            raise UserError(_("Missing Bridge External User."))
        if len(external_user) > 128:
            raise UserError(
                _(
                    "Bridge External User has %d caracters. The maximum is 128 caracters.",
                    len(external_user),
                )
            )
        unallowed_chars = re.sub(r"[a-zA-Z0-9_-]+", "", external_user)
        if unallowed_chars != "":
            raise UserError(
                _(
                    "Bridge External User contains caracters that are not "
                    "accepted: %s. Allowed caracters are letters "
                    "(A to Z, lower and upper case), digits, dash and underscore.",
                    " ".join(list(unallowed_chars)),
                )
            )

        # For some reasons that I can't explain, sudo() doesn't allow
        # to by-pass the record rule and get all company_user_ids
        duplicate_external_user_import_api = (
            self.env["account.statement.import.api"]
            .sudo()
            .search(
                [
                    ("service", "=", "bridge"),
                    ("bridge_external_user_identifier", "=", external_user),
                ],
                limit=1,
            )
        )
        if duplicate_external_user_import_api:
            raise UserError(
                _(
                    "The Bridge External User '%(external_user)s' has already "
                    "been used on statement import API '%(import_api)s' "
                    "of company '%(company)s'.",
                    external_user=external_user,
                    import_api=self.statement_import_api_id.display_name,
                    company=self.company_id.display_name,
                )
            )

        post_json = {"external_user_id": external_user}
        res = self.env["account.statement.import.api"]._bridge_post(
            "aggregation/users",
            speedy["bridge_headers_no_token"],
            result,
            speedy,
            json=post_json,
        )
        if not res.get("external_user_id"):
            ajo._api_import_error_log(
                result,
                "The API call to create a company user didn't return the expected result.",
            )
            return None
        # res has 'uuid' and 'external_user_id'
        # on 25/3/2026, we switch from external_user_id to uuid
        assert res["external_user_id"] == external_user
        vals = {
            "user_identifier": res["uuid"],
            "bridge_external_user_identifier": external_user,
        }
        return vals
