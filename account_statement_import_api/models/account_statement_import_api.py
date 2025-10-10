# Copyright 2025 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.base.models.res_partner import _tz_get

logger = logging.getLogger(__name__)


class AccountStatementImportApi(models.Model):
    _name = "account.statement.import.api"
    _description = "Bank Statement Import API"
    _check_company_auto = True

    company_id = fields.Many2one(
        "res.company",
        required=False,
        ondelete="cascade",
        default=lambda self: self.env.company,
    )
    name = fields.Char(required=True)
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
    service = fields.Selection([], required=True)
    login = fields.Char(string="Login or Client ID", groups="base.group_system")
    password = fields.Char(
        string="Password or Client Secret", groups="base.group_system"
    )
    last_success = fields.Datetime(compute="_compute_last_success")
    backward_days = fields.Integer()  # API-specific module should show/hide it
    show_backward_days = fields.Boolean(compute="_compute_show_backward_days")
    cron_id = fields.Many2one("ir.cron", string="Scheduled Action", readonly=True)
    log_ids = fields.One2many(
        "account.statement.import.api.log",
        "statement_import_api_id",
        readonly=True,
        string="Logs",
    )

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

    @api.depends("journal_ids.statement_import_api_last_success")
    def _compute_last_success(self):
        for rec in self:
            last_success_list = [
                journal.statement_import_api_last_success
                for journal in rec.journal_ids
                if journal.statement_import_api_last_success
            ]
            rec.last_success = last_success_list and max(last_success_list) or False

    @api.model
    def _get_show_backward_days(self, service):
        return True  # key = service ; value = show_backward_days

    @api.depends("service")
    def _compute_show_backward_days(self):
        for rec in self:
            rec.show_backward_days = self._get_show_backward_days(rec.service)

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
            "login": self.login,
            "password": self.password,
            "tz": self.tz and pytz.timezone(self.tz) or pytz.utc,
            "service": self.service,
            "backward_days": self.backward_days,
        }
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
        service2label = dict(
            self.fields_get("service", "selection")["service"]["selection"]
        )
        method_name = f"_{self.service}_test_api"
        if not hasattr(self, method_name):
            raise UserError(
                _(
                    "The test feature has not been implemented for the '%(service)s' API.",
                    service=service2label[self.service],
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
                    service=service2label[self.service],
                ),
                "type": "success",
                "sticky": False,
            },
        }
        return action
