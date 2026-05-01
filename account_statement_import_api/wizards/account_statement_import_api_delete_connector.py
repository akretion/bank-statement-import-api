# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

logger = logging.getLogger(__name__)


class AccountStatementImportApiDeleteConnector(models.TransientModel):
    _name = "account.statement.import.api.delete.connector"
    _description = "Wizard to delete a bank connector"

    statement_import_api_id = fields.Many2one(
        "account.statement.import.api",
        readonly=True,
        required=True,
        string="Bank Statement Import API",
    )
    service = fields.Selection(related="statement_import_api_id.service")
    confirm = fields.Boolean(string="Do you confirm?")
    connector_id = fields.Many2one(
        "account.statement.import.api.connector",
        string="Bank Connector",
        domain="[('statement_import_api_id', '=', statement_import_api_id)]",
        required=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self._context.get("active_model") == "account.statement.import.api":
            import_api_id = self._context.get("active_id")
        elif (
            self._context.get("active_model")
            == "account.statement.import.api.connector"
        ):
            connector_id = self._context.get("active_id")
            res["connector_id"] = connector_id
            connector = self.env["account.statement.import.api.connector"].browse(
                connector_id
            )
            import_api = connector.statement_import_api_id
            import_api_id = import_api.id
        res["statement_import_api_id"] = import_api_id
        return res

    def run(self):
        self.ensure_one()
        if not self.confirm:
            raise UserError(
                _(
                    "You must confirm the deletion of the connector or cancel the operation."
                )
            )
        import_api = self.statement_import_api_id
        connector = self.connector_id
        if connector.statement_import_api_id != import_api:
            raise UserError(
                _(
                    "Connector %(connector)s is not attached to "
                    "statement import API %(import_api)s.",
                    connector.display_name,
                    import_api.display_name,
                )
            )
        speedy = import_api._prepare_speedy()
        method_name = f"_{speedy['service']}_delete_connector"
        result = {"logs": []}
        method = getattr(import_api, method_name)
        method(connector, result, speedy)
        for log_type, msg in result["logs"]:
            if log_type == "error":
                raise UserError(
                    _(
                        "Failed to delete the connector '%(connector)s'. "
                        "Error: %(msg)s",
                        connector=connector.display_name,
                        msg=msg,
                    )
                )
        msg = (
            f"Connector {connector.display_name} has been deleted "
            "on the bank account aggregator side"
        )
        speedy["log_obj"]._info_log(result, msg)
        # Now that connector has been deleted on aggregator side, we delete it in Odoo
        api_accounts = connector.api_account_ids
        for api_account in api_accounts:
            for journal in api_account.journal_ids:
                msg = (
                    f"Detaching API account {api_account.display_name} "
                    f"from bank journal {journal.display_name}"
                )
                speedy["log_obj"]._info_log(result, msg)
                journal.write(
                    {
                        "statement_import_api_id": False,
                        "statement_import_api_account_id": False,
                        "bank_statements_source": False,
                    }
                )
        msg = (
            f"{len(api_accounts)} API account(s) "
            f"{', '.join([x.display_name for x in api_accounts])} deleted in Odoo"
        )
        api_accounts.unlink()
        speedy["log_obj"]._info_log(result, msg)
        msg = f"Connector {connector.display_name} deleted in Odoo"
        connector.unlink()
        speedy["log_obj"]._info_log(result, msg)
        speedy["log_obj"]._create_log("delete_connector", result, speedy)
        logger.info("End of the connector deletion process")
        return
