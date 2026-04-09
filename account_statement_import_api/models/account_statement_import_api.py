# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import pytz

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError

from odoo.addons.base.models.res_partner import _tz_get

logger = logging.getLogger(__name__)


class AccountStatementImportApi(models.Model):
    _name = "account.statement.import.api"
    _description = "Bank Statement Import API"
    _check_company_auto = True

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        ondelete="cascade",
        default=lambda self: self.env.company,
    )
    journal_ids = fields.One2many(
        "account.journal",
        "statement_import_api_id",
        string="Bank Journals",
        check_company=True,
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
        readonly=True,
    )
    tz = fields.Selection(
        _tz_get,
        string="Timezone",
        default=lambda self: self.env.context.get("tz"),
        help="If the API provides datetime fields instead of date fields, Odoo "
        "will use this timezone to translate the datetime to a date.",
    )
    # API-specific modules should show/hide the tz field
    service = fields.Selection("_service_selection", required=True)
    login = fields.Char(
        string="Login or Client ID", groups="base.group_system", copy=False
    )
    password = fields.Char(
        string="Password or Client Secret", groups="base.group_system", copy=False
    )
    last_success = fields.Datetime(compute="_compute_last_success")
    log_ids = fields.One2many(
        "account.statement.import.api.log",
        "statement_import_api_id",
        readonly=True,
        string="Logs",
    )
    api_account_ids = fields.One2many(
        "account.statement.import.api.account",
        "statement_import_api_id",
        string="API Bank Accounts",
    )
    active_api_account_ids = fields.One2many(
        "account.statement.import.api.account",
        "statement_import_api_id",
        string="Active API Bank Accounts",
        domain=[("active", "=", True)],
    )
    inactive_api_account_ids = fields.One2many(
        "account.statement.import.api.account",
        "statement_import_api_id",
        string="Inactive API Bank Accounts",
        domain=[("active", "=", False)],
    )
    connector_ids = fields.One2many(
        "account.statement.import.api.connector",
        "statement_import_api_id",
        string="Bank Connectors",
    )
    user_identifier = fields.Char(
        readonly=True,
        copy=False,
        groups="account.group_account_manager,base.group_system",
    )
    user_identifier_required = fields.Boolean(compute="_compute_show")
    instructions = fields.Html(compute="_compute_show")
    show_manage_accounts_wizard = fields.Boolean(compute="_compute_show")
    show_login = fields.Boolean(compute="_compute_show")
    show_password = fields.Boolean(compute="_compute_show")
    is_aggregator = fields.Boolean(compute="_compute_show")

    _sql_constraints = [
        (
            "name_company_uniq",
            "unique(name, company_id)",
            "A bank statement import API already exists with that name is this company.",
        ),
        (
            "service_user_identifier_uniq",
            "unique(service, user_identifier)",
            "This user identifier already exists for this service.",
        ),
    ]

    @api.model
    def _get_service_info(self):
        service2info = {}
        # in service2info, the required keys are: 'name'
        return service2info

    @api.model
    def _service_selection(self):
        service2info = self._get_service_info()
        res = [(service, info["name"]) for (service, info) in service2info.items()]
        return res

    @api.constrains("service", "login", "password")
    def _check_config(self):
        service2info = self._get_service_info()
        for rec in self:
            if rec.service:
                if rec.service not in service2info:
                    raise ValidationError(_("Service '%s' is unknown.", rec.service))
                info = service2info[rec.service]
                if info.get("login") == "field" and not rec.login:
                    raise ValidationError(
                        _(
                            "Login or Client ID is required for service '%s'.",
                            info["name"],
                        )
                    )
                if info.get("password") == "field" and not rec.password:
                    raise ValidationError(
                        _(
                            "Password or Client Secret is required for service '%s'.",
                            info["name"],
                        )
                    )

    @api.depends("journal_ids.statement_import_api_last_success")
    def _compute_last_success(self):
        for rec in self:
            last_success_list = [
                journal.statement_import_api_last_success
                for journal in rec.journal_ids
                if journal.statement_import_api_last_success
            ]
            rec.last_success = last_success_list and max(last_success_list) or False

    @api.depends("service")
    def _compute_show(self):
        service2info = self._get_service_info()
        for rec in self:
            instructions = False
            is_aggregator = False
            user_identifier_required = False
            show_manage_accounts_wizard = False
            show_login = False
            show_password = False
            if rec.service:
                info = service2info[rec.service]
                instructions = info.get("instructions")
                is_aggregator = info.get("is_aggregator")
                if "user_identifier_required" in info:
                    user_identifier_required = info["user_identifier_required"]
                elif is_aggregator:
                    user_identifier_required = True
                if "manage_accounts_wizard" in info:
                    show_manage_accounts_wizard = info["manage_accounts_wizard"]
                elif is_aggregator:
                    show_manage_accounts_wizard = True
                show_login = info.get("login") == "field"
                show_password = info.get("password") == "field"
            rec.instructions = instructions
            rec.is_aggregator = is_aggregator
            rec.user_identifier_required = user_identifier_required
            rec.show_manage_accounts_wizard = show_manage_accounts_wizard
            rec.show_login = show_login
            rec.show_password = show_password

    def open_cron(self):
        self.ensure_one()
        model = self.env["ir.model"].search(
            [
                ("model", "=", self._name),
                ("transient", "=", False),
            ]
        )
        assert len(model) == 1
        crons = self.env["ir.cron"].search(
            [
                ("model_id", "=", model.id),
                ("state", "=", "code"),
                ("code", "=", f'model.cron_run("{self.service}")'),
            ]
        )
        srv2label = dict(self._fields["service"]._description_selection(self.env))
        if not crons:
            raise UserError(
                _(
                    "No scheduled action found for service '%s'.",
                    srv2label[self.service],
                )
            )
        elif len(crons) > 1:
            raise UserError(
                _(
                    "%(cron_count)s scheduled actions were found for "
                    "service '%(service)s'. There should have "
                    "only one scheduled action for each service.",
                    cron_count=len(crons),
                    service=srv2label[self.service],
                )
            )
        action = self.env["ir.actions.actions"]._for_xml_id("base.ir_cron_act")
        action.update(
            {
                "views": False,
                "view_id": False,
                "res_id": crons.id,
                "view_mode": "form,tree,calendar",
            }
        )
        return action

    @api.model
    def cron_run(self, service):
        logger.info("Start Bank Statement API cron for service {service}")
        import_apis = self.search([("service", "=", service)])
        for import_api in import_apis:
            import_api.run_import()
        logger.info(f"End Bank Statement API cron for service {service}")

    def _prepare_speedy(self):
        self.ensure_one()
        # don't fetch inactive currencies, because we cannot create a bank statement
        # line with an inactive currency (it raises an error)
        currencies_read = self.env["res.currency"].search_read(
            [("active", "=", True)], ["name"]
        )
        currency_code2id = {x["name"]: x["id"] for x in currencies_read}
        speedy = {
            "statement_import_api_id": self.id,
            "currency_code2id": currency_code2id,
            "tz": self.tz and pytz.timezone(self.tz) or pytz.utc,
            "service": self.service,
            "service_info": self._get_service_info()[self.service],
            "login": self.sudo().login,
            "password": self.sudo().password,
        }
        for cred in ("login", "password"):
            if speedy["service_info"].get(cred) == "config_file":
                cred_key = f"account_statement_import_api_{self.service}_{cred}"
                speedy[cred] = tools.config.get(cred_key)
                if not speedy[cred]:
                    raise UserError(
                        _(
                            "Missing key '%(cred_key)s' in the Odoo server configuration file.",
                            cred_key=cred_key,
                        )
                    )
        if (
            not self.env.context.get("no_check_user_identifier")
            and self.user_identifier_required
            and not self.user_identifier
        ):
            raise UserError(
                _(
                    "Missing user identifier on bank statement import API '%s'. "
                    "Click on the button 'Create User'.",
                    self.display_name,
                )
            )
        return speedy

    def run_import(self):
        self.ensure_one()
        logger.info(
            "Start bank statement import API %s company %s",
            self.name,
            self.company_id.display_name,
        )
        speedy = self._prepare_speedy()
        logs_to_create = []
        for journal in self.journal_ids:
            if journal.statement_import_api_account_id:
                if journal.statement_import_api_account_id.active:
                    journal._api_import_bank_statement_lines(speedy)
                else:
                    err_msg = (
                        f"API bank account "
                        f"'{journal.statement_import_api_account_id.display_name}' "
                        f"on journal '{journal.display_name}' is inactive"
                    )
                    logger.warning(err_msg)
                    logs_to_create.append(
                        {
                            "status": "failure",
                            "journal_id": journal.id,
                            "statement_import_api_id": self.id,
                            "logs": err_msg,
                        }
                    )
            else:
                err_msg = (
                    f"API bank account is not set on journal '{journal.display_name}'"
                )
                logger.warning(err_msg)
                logs_to_create.append(
                    {
                        "status": "failure",
                        "journal_id": journal.id,
                        "statement_import_api_id": self.id,
                        "logs": err_msg,
                    }
                )
        if logs_to_create:
            self.env["account.statement.import.api.log"].create(logs_to_create)
        self._connector_status_update(speedy)
        logger.info(
            "End of bank statement import API %s company %s",
            self.name,
            self.company_id.display_name,
        )

    def test_api(self):
        self.ensure_one()
        assert self.service
        speedy = self._prepare_speedy()
        method_name = f"_{self.service}_test_api"
        if not hasattr(self, method_name):
            raise UserError(
                _(
                    "The test feature has not been implemented for the '%(service)s' API.",
                    service=speedy["service_info"]["name"],
                )
            )
        result = {"logs": []}
        method = getattr(self, method_name)
        method(result, speedy)
        for log_type, msg in result["logs"]:
            if log_type == "error":
                raise UserError(
                    _(
                        "The test of the %(service_name)s API failed. Error: %(msg)s",
                        service_name=speedy["service_info"]["name"],
                        msg=msg,
                    )
                )
        action = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": _(
                    "Successful connection to the '%(service_name)s' API.",
                    service_name=speedy["service_info"]["name"],
                ),
                "type": "success",
                "sticky": False,
            },
        }
        return action

    def _get_connector_ident2vals(self, speedy):
        self.ensure_one()
        if not speedy["service_info"].get("is_aggregator"):
            return {}
        result = {"logs": [], "connector_identifier2vals": {}}
        method_name = f"_{self.service}_update_sync_status"
        if not hasattr(self, method_name):
            logger.warning("There is no method %s on %s", method_name, self._name)
            return
        method = getattr(self, method_name)
        connector_ident2vals = method(result, speedy)
        return connector_ident2vals

    def _connector_status_update(self, speedy):
        self.ensure_one()
        if not speedy["service_info"].get("is_aggregator"):
            return
        if not self.connector_ids:
            return
        logger.info(
            "Start connector status update on statement import API %s",
            self.display_name,
        )
        connector_ident2vals = self._get_connector_ident2vals(speedy)
        for connector in self.connector_ids:
            if connector.identifier in connector_ident2vals:
                connector.write(connector_ident2vals[connector.identifier])
                logger.info(
                    "Connector %s in company %s updated",
                    connector.display_name,
                    connector.company_id.display_name,
                )
            else:
                logger.warning(
                    "Identifier %s of connector %s in company %s not retrieved by API",
                    connector.identifier,
                    connector.display_name,
                    connector.company_id.display_name,
                )
        logger.info(
            "End of connector status update on statement import API %s",
            self.display_name,
        )

    def update_api_accounts(self):
        self.ensure_one()
        result = {"logs": []}
        speedy = self._prepare_speedy()
        method_name = f"_{self.service}_update_api_accounts"
        method = getattr(self, method_name)
        account_ident2vals = method(result, speedy)

        for log_type, msg in result["logs"]:
            if log_type == "error":
                raise UserError(
                    _(
                        "Failed to get API bank accounts. Error: %(msg)s",
                        msg=msg,
                    )
                )
        if not account_ident2vals:
            raise UserError(_("No API bank accounts retreived."))
        to_create_vals_list = []
        # 1. clean-up, check and replace currency_code by currency_id
        for account_ident, vals in account_ident2vals.items():
            # clean-up vals
            for key, value in vals.items():
                if value and isinstance(value, str):
                    vals[key] = value.strip()
            if vals.get("account_number") and isinstance(vals["account_number"], str):
                vals["account_number"] = vals["account_number"].replace(" ", "")
            if not account_ident:
                raise UserError(
                    _(
                        "Missing identifier for API bank account %s. This should never happen.",
                        vals,
                    )
                )
            if not isinstance(account_ident, str):
                raise UserError(
                    _(
                        "Account identifier %(ident)s for API bank account %(vals)s "
                        "must be a string.",
                        ident=account_ident,
                        vals=vals,
                    )
                )
            connector_identifier = vals.get("connector_identifier")
            if connector_identifier and not isinstance(connector_identifier, str):
                raise UserError(
                    _(
                        "The field 'connector_identifier' %(connector_identifier)s "
                        "for API bank account vals=%(vals)s ident=%(account_ident)s "
                        "must be a string.",
                        connector_identifier=connector_identifier,
                        vals=vals,
                        account_ident=account_ident,
                    )
                )
            if "currency_code" in vals:
                currency_code = vals.pop("currency_code")
                if currency_code and isinstance(currency_code, str):
                    currency_code = currency_code.upper()
                    if currency_code in speedy["currency_code2id"]:
                        vals["currency_id"] = speedy["currency_code2id"][currency_code]
            if not vals.get("name"):
                raise UserError(
                    _(
                        "Missing 'name' for API bank account %s. This should never happen.",
                        vals,
                    )
                )
        # 2. Update and orphan
        write_count = 0
        archive_count = 0
        for api_account in self.active_api_account_ids:
            if api_account.identifier in account_ident2vals:
                vals = account_ident2vals[api_account.identifier]
                if "connector_identifier" in vals:
                    vals.pop("connector_identifier")
                if (
                    api_account.account_number
                    and api_account.account_number != vals.get("account_number")
                ):
                    raise UserError(
                        _(
                            "API bank account '%(api_account)s' has account number "
                            "'%(cur_account_number)s', but the provider now has a "
                            "different account number '%(new_account_number)s'. "
                            "This should never happen.",
                            api_account=api_account.display_name,
                            cur_account_number=api_account.account_number,
                            new_account_number=vals.get("account_number"),
                        )
                    )
                api_account.write(vals)
                logger.info(
                    "API account %s ID %s updated",
                    api_account.display_name,
                    api_account.id,
                )
                account_ident2vals.pop(api_account.identifier)
                write_count += 1
            else:
                api_account.write({"active": False})
                logger.info("API account %s archived", api_account.display_name)
                archive_count += 1

        # 3. Create
        message_list = []
        if account_ident2vals:
            to_create_vals_list = []
            connector_ident2vals = self._get_connector_ident2vals(speedy)
            conn_obj = self.env["account.statement.import.api.connector"]
            connector_sr = conn_obj.search_read(
                [("statement_import_api_id", "=", self.id)], ["identifier"]
            )
            connector_ident2id = {x["identifier"]: x["id"] for x in connector_sr}
            for account_ident, vals in account_ident2vals.items():
                if "connector_identifier" in vals:
                    connector_identifier = vals.pop("connector_identifier")
                    if not connector_identifier:
                        logger.warning(
                            "connector_identifier is empty in vals=%s "
                            "on statement import API %s",
                            vals,
                            self.display_name,
                        )
                    else:
                        if connector_identifier not in connector_ident2id:
                            if connector_identifier in connector_ident2vals:
                                name = vals.get("bank_name")
                                if not name:
                                    name = f"{connector_identifier} (TO RENAME)"
                                connector = conn_obj.create(
                                    dict(
                                        connector_ident2vals[connector_identifier],
                                        identifier=connector_identifier,
                                        statement_import_api_id=self.id,
                                        name=name,
                                    )
                                )
                                logger.info(
                                    "Connector %s ID %s created",
                                    connector.display_name,
                                    connector.id,
                                )
                                connector_ident2id[connector_identifier] = connector.id
                                vals["connector_id"] = connector.id
                            else:
                                logger.warning(
                                    "connector_identifier %s is not in connector_ident2vals",
                                    connector_identifier,
                                )
                        else:
                            vals["connector_id"] = connector_ident2id[
                                connector_identifier
                            ]
                vals.update(
                    {
                        "identifier": account_ident,
                        "statement_import_api_id": self.id,
                    }
                )
                to_create_vals_list.append(vals)
            if to_create_vals_list:
                self.env["account.statement.import.api.account"].create(
                    to_create_vals_list
                )
                logger.info(
                    "%d API bank account(s) created on statement import API %s",
                    len(to_create_vals_list),
                    self.display_name,
                )
                message_list.append(
                    _("%d API bank accounts created.", len(to_create_vals_list))
                )

        if write_count:
            message_list.append(_("%d API bank accounts updated.", write_count))
        if archive_count:
            message_list.append(_("%d API bank accounts archived.", archive_count))
        action_next = self.env["ir.actions.actions"]._for_xml_id(
            "account_statement_import_api.account_statement_import_api_action"
        )
        action_next.update(
            {
                "views": [x for x in action_next["views"] if x and x[1] == "form"],
                "view_mode": "form",
                "res_id": self.id,
            }
        )
        action = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "title": _("Successful Update"),
                "message": "\n".join(message_list),
                "next": action_next,
            },
        }
        return action

    def _prepare_delete_user(self):
        """This method is designed to be inherited by service-specific modules"""
        return {"user_identifier": False}
