# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import pytz

from odoo import _, api, fields, models
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
    company_user_ids = fields.One2many(
        "account.statement.import.api.company.user",
        "statement_import_api_id",
        string="Per-Company Users",
    )
    show_company_user = fields.Boolean(compute="_compute_show")
    instructions = fields.Html(compute="_compute_show")

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
                    raise ValidationError(_("Service '%s' is unknown.") % rec.service)
                info = service2info[rec.service]
                if info.get("company_required") and not rec.company_id:
                    raise ValidationError(
                        _("Company is required for service '%s'.") % info["name"]
                    )
                if info.get("login_required") and not rec.login:
                    raise ValidationError(
                        _("Login or Client ID is required for service '%s'.")
                        % info["name"]
                    )
                if info.get("password_required") and not rec.password:
                    raise ValidationError(
                        _("Password or Client Secret is required for service '%s'.")
                        % info["name"]
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
            if rec.service:
                info = service2info[rec.service]
                show_backward_days = info.get("show_backward_days", True)
                show_company_user = info.get("user_company_required", True)
                instructions = info.get("instructions")
            rec.show_backward_days = show_backward_days
            rec.show_company_user = show_company_user
            rec.instructions = instructions

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
        currencies_read = (
            self.env["res.currency"]
            .with_context(active_test=False)
            .search_read([], ["name"])
        )
        currency_code2id = {x["name"]: x["id"] for x in currencies_read}
        speedy = {
            "statement_import_api_id": self.id,
            "currency_code2id": currency_code2id,
            "login": self.sudo().login,
            "password": self.sudo().password,
            "tz": self.tz and pytz.timezone(self.tz) or pytz.utc,
            "service": self.service,
            "service_info": self._get_service_info()[self.service],
            "backward_days": self.backward_days,
        }
        if speedy["service_info"].get("user_company_required"):
            self._check_company_user_identifier()
            speedy["company_id2token"] = {}
        return speedy

    def _update_speedy(self, journal, speedy):
        assert journal

    def run_import(self):
        self.ensure_one()
        logger.info("Start bank statement import API %s", self.name)
        speedy = self._prepare_speedy()
        for journal in self.journal_ids:
            journal._api_import_bank_statement_lines(speedy)
        logger.info("End of bank statement import API %s", self.name)

    def test_api(self):
        self.ensure_one()
        assert self.service
        service_info = self._get_service_info()[self.service]
        if service_info.get("user_company_required"):
            self._check_company_user_identifier()
        method_name = f"_{self.service}_test_api"
        if not hasattr(self, method_name):
            raise UserError(
                _(
                    "The test feature has not been implemented for the '%(service)s' API.",
                    service=service_info["name"],
                )
            )
        method = getattr(self, method_name)
        method()
        action = {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": _(
                    "Successful connection to the '%(service)s' API.",
                    service=service_info["name"],
                ),
                "type": "success",
                "sticky": False,
            },
        }
        return action

    def update_api_accounts(self):
        self.ensure_one()
        result = {"logs": []}
        speedy = self._prepare_speedy()
        if not self.service:
            raise UserError(
                _("Missing service on bank statement import API '%s'.")
                % self.display_name
            )
        method_name = f"_update_api_accounts_{self.service}"
        method = getattr(self, method_name)
        res = method(result, speedy)
        # res is a list of vals of account.statement.import.api.set.identifier.line
        if not res:
            raise UserError(result["logs"][-1][1])
        api_acc_obj = self.env["account.statement.import.api.account"]
        existing_identifiers_read = api_acc_obj.with_context(
            active_test=False
        ).search_read([("statement_import_api_id", "=", self.id)], ["identifier"])
        identifier2id = {x["identifier"]: x["id"] for x in existing_identifiers_read}
        identifier2id_orphaned = dict(identifier2id)
        to_create_vals_list = []
        to_activate_ids = []
        for vals in res:
            # clean-up vals
            for key, value in vals.items():
                if value and isinstance(value, str):
                    vals[key] = value.strip()
            if vals.get("account_number") and isinstance(vals["account_number"], str):
                vals["account_number"] = vals["account_number"].replace(" ", "")
            if not vals.get("identifier"):
                raise UserError(
                    _(
                        "Missing identifier for API bank account %s. This should never happen."
                    )
                    % vals
                )
            if isinstance(vals["identifier"], int):
                vals["identifier"] = str(vals["identifier"])
            if not vals.get("name"):
                raise UserError(
                    _(
                        "Missing 'name' for API bank account %s. This should never happen."
                    )
                    % vals
                )
            if vals["identifier"] in identifier2id_orphaned:
                identifier2id_orphaned.pop(vals["identifier"])
            if vals["identifier"] in identifier2id:
                to_activate_ids.append(identifier2id[vals["identifier"]])
            else:
                to_create_vals_list.append(dict(vals, statement_import_api_id=self.id))
                logger.info(
                    "Identifier %s doesn't exist on statement import API ID %s. "
                    "Will be created.",
                    vals["identifier"],
                    self.id,
                )
        if to_create_vals_list:
            new_api_bank_accounts = api_acc_obj.create(to_create_vals_list)
            logger.info(
                "%d API bank account(s) created on statement import API ID %s",
                len(new_api_bank_accounts),
                self.id,
            )
        if to_activate_ids:
            to_activate_api_bank_accounts = api_acc_obj.browse(to_activate_ids)
            to_activate_api_bank_accounts.write({"active": True})
        if identifier2id_orphaned:
            to_archive_api_bank_accounts = api_acc_obj.browse(
                list(identifier2id_orphaned.values())
            )
            to_archive_api_bank_accounts.write({"active": False})
            logger.info(
                "%d API bank account(s) archived on statement import API ID %s",
                len(to_archive_api_bank_accounts),
                self.id,
            )

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
                    "Missing per-company user identifier for the following companies:\n%s."
                )
                % "\n".join(
                    [f"- {company.display_name}" for company in companies_missing_user]
                )
            )
