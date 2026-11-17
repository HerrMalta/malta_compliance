### Malta Compliance

Malta tax helpers for ERPNext: income tax, provisional tax and social security contributions (SSC)

### Company setup for a self-employed individual

`malta_compliance.setup.company.setup_company` sets up an ERPNext company for a self-employed individual in Malta:

- a chart of accounts (`setup/chart_self_employed.json`) with revenue split by place of supply, expense categories, VAT accounts, capital allowances, and owner capital and drawings;
- tax categories named after the boxes of the Maltese VAT return, and for a registration under Article 10 the sales and purchase tax templates of those categories, reverse charge included (`setup/vat.py`); an Article 11 company receives no templates and books purchases gross;
- bank accounts, company address, fiscal years, default accounts, a service item, and the Sales Invoice field "Original Invoice No" for invoices issued outside ERPNext.

The function is idempotent and takes all personal data as arguments:

```bash
bench --site <site> execute malta_compliance.setup.company.setup_company --kwargs '{"company_name": "...", "abbr": "...", "vat_article": 10, "tax_id": "MT...", "banks": [{"bank": "...", "swift_number": "...", "account_name": "...", "account_number": "1110", "iban": "..."}], "fiscal_years": [2025, 2026]}'
```

`malta_compliance.setup.vat.boxes()` returns the VAT return boxes of each tax category.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/HerrMalta/malta_compliance --branch main
bench install-app malta_compliance
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/malta_compliance
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

MIT
