.. image:: https://img.shields.io/badge/license-AGPL--3-blue.png
   :target: https://www.gnu.org/licenses/agpl
   :alt: License: AGPL-3

============================
Bank Statement Import by API
============================

This is the base module for bank statement line import by API. This module doesn't do anything by itself, it requires additional modules to add support for specific banks or bank aggregators. At this time, 3 modules are available:

* **account_statement_import_api_bridge**: a connector with `BridgeAPI <https://www.bridgeapi.io/>`_, a bank aggregator,
* **account_statement_import_api_powens**: a connector with `Powens <https://www.powens.com/>`_, a bank aggregator,
* **account_statement_import_api_qonto**: a connector with the neobank `Qonto <https://qonto.com/>`_.

This module is an alternative to the OCA module **account_statement_import_online**. I have explained the reasons why I decided to re-write this module in `this comment <https://github.com/OCA/bank-statement-import/pull/502#issuecomment-1374252853>`_. In addition to the reasons I explained at that time, there is another very important reason: add suport for the update of already downloaded bank statement lines. This feature is not useful for traditionnal banks, but it is important for modern online banks that allow to have additional information attached to bank statement line that can be added by users (pictures or attachments, custom label, analytic accounts, VAT amounts, etc.). These additional information can be added/updated by the user after the import of the bank statement line in Odoo: if the bank statement line hasn't be reconciled yet, Odoo will update the additional information attached to the bank statement line in Odoo.

This implementation has taken particular care on giving the maximum information to users about what happens in the background (or when executed manually): the logs of all actions (download of bank statement lines, check of account balance, update of bank connectors status for bank aggregators, etc) are available to users in the web interface of Odoo. This make it much easier to understand problems when they occur. The aim is to kill the *black box effect* and give control back to the user.

Bug Tracker
===========

Bugs are tracked on `GitHub Issues
<https://github.com/akretion/bank-statement-import-api/issues>`_. In case of trouble, please
check there if your issue has already been reported. If you spotted it first,
help us smashing it by providing a detailed and welcomed feedback.

Credits
=======

Contributors
------------

* Alexis de Lattre <alexis.delattre@akretion.com>

