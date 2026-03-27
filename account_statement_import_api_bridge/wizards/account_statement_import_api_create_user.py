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

    bridge_external_user = fields.Char(
        compute="_compute_bridge_external_user",
        store=True,
        readonly=False,
        precompute=True,
        help="Allowed chars: letters (A to Z, lower and upper case), "
        "digits, dash and underscore.",
        size=128,
    )

    @api.depends("company_id")
    def _compute_bridge_external_user(self):
        for wiz in self:
            bridge_external_user = False
            if wiz.company_id:
                company_name = unidecode(wiz.company_id.name).lower().replace(" ", "_")
                bridge_external_user = "".join(
                    re.findall(r"[a-zA-Z0-9_-]+", company_name)
                )[:128]
            wiz.bridge_external_user = bridge_external_user

    def _bridge_create_user(self, result, speedy):
        ajo = self.env["account.journal"]
        external_user = self.bridge_external_user and self.bridge_external_user.strip()
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
        for company_user in self.statement_import_api_id.sudo().company_user_ids:
            if company_user.identifier == external_user:
                raise UserError(
                    _(
                        "The Bridge External User '%(external_user)s' has already "
                        "been used on company '%(company)s'.",
                        external_user=external_user,
                        company=self.company_id.display_name,
                    )
                )

        post_json = {"external_user_id": external_user}
        headers = self.statement_import_api_id._bridge_get_headers_no_token(speedy)
        res = self.env["account.statement.import.api"]._bridge_post(
            "aggregation/users", headers, result, speedy, json=post_json
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
        company_user_vals = {
            "identifier": res["uuid"],
            "bridge_external_identifier": external_user,
        }
        return company_user_vals
