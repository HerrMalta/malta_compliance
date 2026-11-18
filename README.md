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

### Capital allowances

ERPNext's asset module computes the Maltese tax depreciation for assets of the categories `CA 01` to `CA 18` (the Schedule to S.L. 123.01), `CA IP` (intellectual property, ITA art. 14(1)(m)) and `CA IB` (industrial buildings and structures); `CA Land` carries no allowance. The legal basis, with citations and the points no source settles, is in [docs/capital-allowances.md](docs/capital-allowances.md). `setup_company` creates the categories, their accounts and one fixed-asset Item per category; the patch of version 0.3.0 adds them to companies set up earlier.

- **Schedule**: straight line over the minimum number of years of the category (more years are accepted), a full year in the year of first use (the Available-for-use Date), no allowance in the year of disposal unless the asset leaves on the last day of the fiscal year. Industrial buildings: 2% a year plus 10% in the first year, unless "No Initial Allowance" is set. Intellectual property: at least 3 years, or the whole cost in the year of first use with "Deduct in One Year".
- **Private use and vehicle cap**: the business use of an asset ("Business Use", per fiscal year in "Business Use per Year") and the EUR 14,000 cap of S.L. 123.07 rule 3 for cars ("Vehicle Outside the Cost Cap" for vehicles outside rule 3(4)) reduce the allowance. For each depreciation entry an adjustment entry moves the private share to 3200 Drawings and the capped excess to 3240 Non-deductible Capital Allowances.
- **Disposals**: a sale through a Sales Invoice, or scrapping (with "Disposal Value" for an asset taken into private use), is followed by an adjustment that brings the result on 6200 to the balancing allowance or charge of ITA art. 24, with proceeds of a capped vehicle apportioned by 14,000 / cost. Results outside the balancing statement (intellectual property, assets without any allowance, proceeds above cost) go to 3240. ERPNext rejects a disposal dated before a booked year-end depreciation entry; that entry is cancelled first, which cancels its adjustment as well.
- **Accounts and return**: 6100 (wear and tear), 6120 (industrial buildings) and 6110 (intellectual property) correspond to lines 24, 23 and 22 of the MTCA profit and loss form. The profit in ERPNext equals the taxable profit of the source before the limits of the tax computation: unabsorbed allowances (art. 14(1)(f) proviso (ii)) and part (b) of the one-year option above the income produced by the asset.
- **Report** "Capital Allowances Malta": allowances, deductible amounts and tax written-down values per asset and fiscal year, the balancing statements of the year, and the check of part (b) of the one-year option.
- **Not covered**: the replacement election of art. 24(3), finance leases and leased vehicles (lease payments are expenses), assets first used before 2001 and aircraft acquired before 2018. Value adjustments, capitalised repairs, longer asset lives, asset capitalization and splits are rejected for these categories; an improvement is a separate asset.

The rules are held with their periods of validity in `malta_compliance/assets/rules.py`. Values tied to acquisition or first use are frozen on the asset when it is submitted, so a later change of the law leaves existing assets unchanged. `REVIEWED_UP_TO` names the last year of assessment checked against the law; later years produce a warning. `tools/law_check.py` compares the consolidated texts on legislation.mt with `malta_compliance/assets/law_versions.json`; the workflow `.github/workflows/law-check.yml` runs it monthly and opens an issue on a change.

Tests, on a test site with ERPNext and the setup wizard completed:

```bash
bench --site <test site> run-tests --module malta_compliance.tests.test_capital_allowances
```

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
