.. image:: https://img.shields.io/badge/license-AGPL--3-blue.png
   :target: https://www.gnu.org/licenses/agpl
   :alt: License: AGPL-3

=========================================================
Vendor Bill support in Bank Statement Reconcile Interface
=========================================================

This module adds support for the creation of vendor bills in the OCA bank statement reconcile interface (OCA module **account_reconcile_oca** available in the Github projet `account-reconcile <https://github.com/OCA/account-reconcile/>`_).

This feature is useful for modern banks that allow to have additional information attached to bank statement line that can be added by users:

- pictures and/or attachments,
- expense category,
- custom expense description,
- analytic accounts,
- VAT rates and amounts.

With these additional information, the module can create a vendor bill with a single line directly from the bank statement reconcile interface and auto-reconcile this vendor bill with the bank statement line. This is particularly useful to handle professionnal expenses paid by card.

This module is currently used by the `Qonto <https://qonto.com/>`_ connector.

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

