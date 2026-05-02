
<!-- /!\ Non OCA Context : Set here the badge of your runbot / runboat instance. -->
[![Pre-commit Status](https://github.com/akretion/bank-statement-import-api/actions/workflows/pre-commit.yml/badge.svg?branch=16.0)](https://github.com/akretion/bank-statement-import-api/actions/workflows/pre-commit.yml?query=branch%3A16.0)
[![Build Status](https://github.com/akretion/bank-statement-import-api/actions/workflows/test.yml/badge.svg?branch=16.0)](https://github.com/akretion/bank-statement-import-api/actions/workflows/test.yml?query=branch%3A16.0)
[![codecov](https://codecov.io/gh/akretion/bank-statement-import-api/branch/16.0/graph/badge.svg)](https://codecov.io/gh/akretion/bank-statement-import-api)
<!-- /!\ Non OCA Context : Set here the badge of your translation instance. -->

<!-- /!\ do not modify above this line -->

# Bank Statement Import by API

New generation modules for Bank Statement Import by API

<!-- /!\ do not modify below this line -->

<!-- prettier-ignore-start -->

[//]: # (addons)

Available addons
----------------
addon | version | maintainers | summary
--- | --- | --- | ---
[account_statement_import_api](account_statement_import_api/) | 16.0.3.0.0 | <a href='https://github.com/alexis-via'><img src='https://github.com/alexis-via.png' width='32' height='32' style='border-radius:50%;' alt='alexis-via'/></a> | Base module to download bank statement via an API
[account_statement_import_api_bridge](account_statement_import_api_bridge/) | 16.0.2.0.0 | <a href='https://github.com/alexis-via'><img src='https://github.com/alexis-via.png' width='32' height='32' style='border-radius:50%;' alt='alexis-via'/></a> | Use BridgeAPI.io to download bank statement lines
[account_statement_import_api_qonto](account_statement_import_api_qonto/) | 16.0.1.0.0 | <a href='https://github.com/alexis-via'><img src='https://github.com/alexis-via.png' width='32' height='32' style='border-radius:50%;' alt='alexis-via'/></a> | Use the Qonto API to download bank statement lines
[account_statement_import_in_invoice](account_statement_import_in_invoice/) | 16.0.1.0.0 | <a href='https://github.com/alexis-via'><img src='https://github.com/alexis-via.png' width='32' height='32' style='border-radius:50%;' alt='alexis-via'/></a> | Enrich bank statement lines to allow the creation of vendor bills
[account_statement_import_in_invoice_api](account_statement_import_in_invoice_api/) | 16.0.1.0.0 | <a href='https://github.com/alexis-via'><img src='https://github.com/alexis-via.png' width='32' height='32' style='border-radius:50%;' alt='alexis-via'/></a> | Glue module between account_statement_import_in_invoice and account_statement_import_api
[account_statement_import_in_invoice_start_end_dates](account_statement_import_in_invoice_start_end_dates/) | 16.0.1.0.0 | <a href='https://github.com/alexis-via'><img src='https://github.com/alexis-via.png' width='32' height='32' style='border-radius:50%;' alt='alexis-via'/></a> | Glue module between account_statement_import_in_invoice and account_invoice_start_end_dates


Unported addons
---------------
addon | version | maintainers | summary
--- | --- | --- | ---
[account_statement_import_api_powens](account_statement_import_api_powens/) | 16.0.1.0.0 (unported) | <a href='https://github.com/alexis-via'><img src='https://github.com/alexis-via.png' width='32' height='32' style='border-radius:50%;' alt='alexis-via'/></a> | Use Powens to download bank statement lines

[//]: # (end addons)

<!-- prettier-ignore-end -->

## Licenses

This repository is licensed under [AGPL-3.0](LICENSE).

However, each module can have a totally different license, as long as they adhere to Akretion
policy. Consult each module's `__manifest__.py` file, which contains a `license` key
that explains its license.

----
<!-- /!\ Non OCA Context : Set here the full description of your organization. -->
