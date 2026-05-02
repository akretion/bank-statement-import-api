# Copyright 2025 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

logger = logging.getLogger(__name__)


def update_bank_statement_expense_categ(env):
    exp_obj = env["account.bank.statement.expense.categ"]
    acc_obj = env["account.account"]
    exp_categs = exp_obj.search([("service", "=", "qonto")])
    mapping = exp_obj._qonto_account_mapping()
    for company in env["res.company"].search([]):
        if not company.country_id:
            logger.warning("Country is not set on company %s", company.display_name)
            continue
        if company.country_id.code in mapping:
            logger.info(
                "Setting accounts on qonto bank statement expense categ in company %s",
                company.display_name,
            )
            for exp_categ in exp_categs:
                if exp_categ.code in mapping[company.country_id.code]:
                    account_code = mapping[company.country_id.code][exp_categ.code]
                    account = acc_obj.with_company(company.id).search(
                        [
                            ("code", "=like", f"{account_code}%"),
                            ("company_ids", "in", company.id),
                            ("deprecated", "=", False),
                        ],
                        limit=1,
                    )
                    if account:
                        exp_categ.with_company(company.id).write(
                            {"account_id": account.id}
                        )
                    else:
                        logger.info(
                            "No account found with code that starts with %s in company %s",
                            account_code,
                            company.display_name,
                        )
        else:
            logger.info(
                "No accounting pre-config for qonto bank statement expense categ "
                "for company %s country code %s",
                company.display_name,
                company.country_id.code,
            )
    return
