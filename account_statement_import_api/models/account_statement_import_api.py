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
        required=False,
        ondelete="cascade",
        compute="_compute_company_id",
        store=True,
        readonly=False,
        precompute=True,
    )
    journal_ids = fields.One2many(
        "account.journal",
        "statement_import_api_id",
        string="Bank Journals",
        check_company=True,
        domain="[('type', '=', 'bank')]",
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
    login = fields.Char(string="Login or Client ID", groups="base.group_system")
    password = fields.Char(
        string="Password or Client Secret", groups="base.group_system"
    )
    last_success = fields.Datetime(compute="_compute_last_success")
    backward_days = fields.Integer()  # API-specific module should show/hide it
    show_backward_days = fields.Boolean(compute="_compute_show")
    cron_id = fields.Many2one("ir.cron", string="Scheduled Action", readonly=True)
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
    company_user_ids = fields.One2many(
        "account.statement.import.api.company.user",
        "statement_import_api_id",
        string="Per-Company Users",
    )
    show_company_user = fields.Boolean(compute="_compute_show")
    instructions = fields.Html(compute="_compute_show")
    show_add_account_wizard = fields.Boolean(compute="_compute_show")
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
            "backward_days_positive",
            "CHECK(backward_days >= 0)",
            "Backward days must be positive or null.",
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

    @api.constrains("service", "login", "password", "company_id")
    def _check_config(self):
        service2info = self._get_service_info()
        for rec in self:
            if rec.service:
                if rec.service not in service2info:
                    raise ValidationError(_("Service '%s' is unknown.", rec.service))
                info = service2info[rec.service]
                if info.get("company_required") and not rec.company_id:
                    raise ValidationError(
                        _("Company is required for service '%s'.", info["name"])
                    )
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
            show_backward_days = True
            show_company_user = True
            instructions = False
            show_add_account_wizard = False
            show_manage_accounts_wizard = False
            is_aggregator = False
            show_login = False
            show_password = False
            if rec.service:
                info = service2info[rec.service]
                show_backward_days = info.get("show_backward_days", True)
                show_company_user = info.get("user_company_required", True)
                instructions = info.get("instructions")
                show_add_account_wizard = info.get(
                    "user_company_required", True
                )  # TODO
                show_manage_accounts_wizard = info.get("manage_accounts_wizard")
                is_aggregator = info.get("is_aggregator")
                show_login = info.get("login") == "field"
                show_password = info.get("password") == "field"
            rec.show_backward_days = show_backward_days
            rec.show_company_user = show_company_user
            rec.instructions = instructions
            rec.show_add_account_wizard = show_add_account_wizard
            rec.show_manage_accounts_wizard = show_manage_accounts_wizard
            rec.is_aggregator = is_aggregator
            rec.show_login = show_login
            rec.show_password = show_password

    @api.depends("service")
    def _compute_company_id(self):
        service2info = self._get_service_info()
        for rec in self:
            if (
                rec.service
                and not rec.company_id
                and service2info[rec.service].get("company_required")
            ):
                rec.company_id = self.env.company.id

    def _prepare_cron(self):
        self.ensure_one()
        model = self.env["ir.model"].search(
            [
                ("model", "=", self._name),
                ("transient", "=", False),
            ]
        )
        assert len(model) == 1
        name = f"Bank Statement API: {self.name}"
        if self.company_id:
            name = f"{name} (company {self.company_id.name})"
        vals = {
            "name": name,
            "active": True,
            "user_id": self.env.ref("base.user_root").id,
            "interval_number": 1,
            "interval_type": "days",
            "numbercall": -1,  # remove when porting in v18
            "model_id": model.id,
            "state": "code",
            "code": "model.cron_run(%s)" % self.id,
        }
        return vals

    def create_cron(self):
        self.ensure_one()
        assert not self.cron_id
        cron = self.env["ir.cron"].create(self._prepare_cron())
        self.write({"cron_id": cron.id})

    @api.model
    def cron_run(self, import_api_id):
        import_api = self.browse(import_api_id)
        logger.info("Start Bank Statement API cron %s", import_api.name)
        import_api.run_import()
        logger.info("End Bank Statement API cron %s", import_api.name)

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
            "backward_days": self.backward_days,
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
        if speedy["service_info"].get("user_company_required"):
            self._check_company_user_identifier()
            speedy["company_id2token"] = {}
            speedy["company_id2user_identifier"] = {}
            for company_user in self.sudo().company_user_ids:
                company_id = company_user.company_id.id
                speedy["company_id2user_identifier"][
                    company_id
                ] = company_user.identifier

        return speedy

    def run_import(self):
        self.ensure_one()
        logger.info("Start bank statement import API %s", self.name)
        speedy = self._prepare_speedy()
        for journal in self.journal_ids:
            journal._api_import_bank_statement_lines(speedy)
        self._connector_status_update(speedy)
        logger.info("End of bank statement import API %s", self.name)

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
        method_name = f"_update_sync_status_{speedy['service']}"
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
                    "Connector %s of bank statement import API %s updated",
                    connector.display_name,
                    self.display_name,
                )
            else:
                logger.warning(
                    "Identifier %s of connector %s of bank statement "
                    "import API %s not retrieved by API",
                    connector.identifier,
                    connector.display_name,
                    self.display_name,
                )
        logger.info(
            "Connector status update on statement import API %s finished",
            self.display_name,
        )

    def update_api_accounts(self):
        self.ensure_one()
        result = {"logs": []}
        speedy = self._prepare_speedy()
        company = self.company_id or self.env.company
        method_name = f"_update_api_accounts_{speedy['service']}"
        method = getattr(self, method_name)
        account_ident2vals = method(company, result, speedy)
        if not account_ident2vals:
            raise UserError(result["logs"][-1][1])
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
                                    name = f"{connector_identifier} TODO rename"
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

    def _check_company_user_identifier(self):
        self.ensure_one()
        companies_missing_user = set()
        for journal in self.journal_ids:
            companies_missing_user.add(journal.company_id)
        for company_user in self.company_user_ids:
            if company_user.company_id in companies_missing_user:
                companies_missing_user.remove(company_user.company_id)
        if companies_missing_user:
            raise UserError(
                _(
                    "Missing per-company user identifier for the following companies:\n%s.",
                    "\n".join(
                        [
                            f"- {company.display_name}"
                            for company in companies_missing_user
                        ]
                    ),
                )
            )
