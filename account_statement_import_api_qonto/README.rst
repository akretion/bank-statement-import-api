.. image:: https://img.shields.io/badge/license-AGPL--3-blue.png
   :target: https://www.gnu.org/licenses/agpl
   :alt: License: AGPL-3

====================
Odoo-Qonto connector
====================

This is the connector between Odoo and `Qonto <https://qonto.com/>`_, a european neobank. This is an alternative to the OCA module **account_statement_import_online_qonto** available on the Github project `bank-statement-import <https://github.com/OCA/bank-statement-import>`_. The main advantage of this module is that it supports the additional data of Qonto bank statement lines:

- pictures and/or attachments,
- expense category,
- custom expense description,
- analytic accounts,
- VAT rates and amounts.

Thanks to these additional information, when the user is on a Qonto bank statement line in the OCA bank statement reconcile interface, he will be able to:

- create a vendor bill,
- process the bank statement line,
- reconcile the vendor bill with the bank statement line,

in a single click ! This is a big time-saver !

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

