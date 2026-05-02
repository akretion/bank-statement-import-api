import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo-addons-akretion-bank-statement-import-api",
    description="Meta package for akretion-bank-statement-import-api Odoo addons",
    version=version,
    install_requires=[
        'odoo-addon-account_statement_import_api>=16.0dev,<16.1dev',
        'odoo-addon-account_statement_import_api_bridge>=16.0dev,<16.1dev',
        'odoo-addon-account_statement_import_api_qonto>=16.0dev,<16.1dev',
        'odoo-addon-account_statement_import_in_invoice>=16.0dev,<16.1dev',
        'odoo-addon-account_statement_import_in_invoice_api>=16.0dev,<16.1dev',
        'odoo-addon-account_statement_import_in_invoice_start_end_dates>=16.0dev,<16.1dev',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
        'Framework :: Odoo :: 16.0',
    ]
)
