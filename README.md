### Malta Compliance

Malta tax helpers for ERPNext: income tax, provisional tax and social security contributions (SSC)

### Desk

The entry "Malta Compliance" on ERPNext's rail, the column of module icons at the left of the desk, opens the sidebar "Malta Compliance" with Malta Taxpayer, Malta Tax Year and the five reports. The Dock record `malta_compliance/dock/malta_compliance/malta_compliance.json` mounts the entry on ERPNext's rail; Frappe shows no apps-screen tile for a mounted app. The icons of the entry and of the sidebar header are in `malta_compliance/public/icons/module-icons.svg`.

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

- **Schedule**: straight line over the minimum number of years of the category (more years are accepted), a full year in the year of first use (the Available-for-use Date), no allowance in the year of disposal unless the asset leaves on the last day of the fiscal year. Industrial buildings: 2% a year, plus 10% in the first year for a building entered as "New building, not used before" in the required field "Building Condition". Intellectual property: at least 3 years, or the whole cost in the year of first use with "Deduct in One Year"; the instalment of the year of a sale is deducted.
- **Private use and vehicle cap**: the business use of an asset ("Business Use", per fiscal year in "Business Use per Year") and the EUR 14,000 cap of S.L. 123.07 rule 3 for cars ("Vehicle Outside the Cost Cap" for vehicles outside rule 3(4)) reduce the allowance. For each depreciation entry an adjustment entry moves the private share to 3200 Drawings and the capped excess to 3240 Non-deductible Capital Allowances.
- **Disposals**: a sale through a Sales Invoice, or scrapping (with "Disposal Value" for an asset taken into private use), is followed by an adjustment that brings the result on 6200 to the balancing allowance or charge of ITA art. 24, with proceeds of a capped vehicle apportioned by 14,000 / cost. Results outside the balancing statement (intellectual property, assets without any allowance, proceeds above cost) go to 3240; for intellectual property the report shows the capital gain of ITA art. 5 on the cost less the deductions claimed. ERPNext rejects a disposal dated before a booked year-end depreciation entry; that entry is cancelled first, which cancels its adjustment as well.
- **Choice of category**: software bought as a licence to use is `CA 02` (4 years); `CA IP` is meant for software whose copyright or exclusive licence the business holds. An asset brought into the business from private ownership is entered at its open-market value on the date of first business use, not above its original cost, with that date as Available-for-use Date. Both are readings of the law without an official statement (docs/capital-allowances.md, "Readings").
- **Accounts and return**: 6100 (wear and tear), 6120 (industrial buildings) and 6110 (intellectual property) correspond to lines 24, 23 and 22 of the MTCA profit and loss form. The profit in ERPNext equals the taxable profit of the source before the limits of the tax computation: unabsorbed allowances (art. 14(1)(f) proviso (ii)) and part (b) of the one-year option above the income produced by the asset.
- **Report** "Capital Allowances Malta": allowances, deductible amounts and tax written-down values per asset and fiscal year, the balancing statements of the year, and the check of part (b) of the one-year option.
- **Not covered**: the replacement election of art. 24(3), finance leases and leased vehicles (lease payments are expenses), assets first used before 2001 and aircraft acquired before 2018. Value adjustments, capitalised repairs, longer asset lives, asset capitalization and splits are rejected for these categories; an improvement is a separate asset.

The rules are held with their periods of validity in `malta_compliance/assets/rules.py`. Values tied to acquisition or first use are frozen on the asset when it is submitted, so a later change of the law leaves existing assets unchanged. `REVIEWED_UP_TO` names the last year of assessment checked against the law; later years produce a warning.

### Income tax, provisional tax and Class 2 contributions

The record "Malta Taxpayer" holds the facts of a taxpayer, or of a married couple, that hold for every year. The record "Malta Tax Year" holds the return data of one basis year; a year without such a record is built from the Malta Taxpayer and the books. Four reports compute from them. The legal basis, with citations and the points not settled by any source, is in [docs/income-tax.md](docs/income-tax.md). The scope is a resident self-employed individual, single or married, with trade income taxed at the rates of ITA art. 56(1).

- **Malta Taxpayer**: tax status, qualifying children, per person the year of birth and the dates of the self-occupation, the companies in the books with the person carrying on each trade, and one row per filed return (net profit of each spouse, chargeable income, tax charged). A year with a filed return takes its profits and tax from that row, any other year the profit of the listed companies from the books; the net profits of a filed return are the Class 2 base of the following year. The first year of a self-occupation is charged at the lowest Class 2 rate.
- **Malta Tax Year**: tax status (single, married, single parent), qualifying children, the companies whose profit enters the return with the spouse carrying on each trade, amounts outside the books (trade profit, employment or pension income, other income, deductions, tax credits, tax at source), the payments made in the basis year, and the figures of the return as filed. It is needed only where a year differs from the Malta Taxpayer, such as payments made outside the books; a saved record of a year takes precedence over the year built from the Malta Taxpayer. The field "Taxpayer" links to the Malta Taxpayer: once it and the basis year are chosen, a new record is filled with the values the reports would build for that year, and the records of the other years of the same taxpayer are found by it.
- **Profit**: income less expenses of each listed company in the calendar year, without the interest income on account 4920, which the report names separately. Each income and expense account is rounded to the nearest euro, and the profit is the sum of the rounded accounts, as in a profit and loss account presented in whole euro. The taxpayer's own Class 2 contributions and tax payments belong on the equity accounts 3220 and 3210 and are not deducted; account 5950 is for contributions paid for employees.
- **Payments**: "Get Payments from the Books" lists the payments booked in the basis year on 3210 and 3220 of the listed companies; a built year reads them directly. Each payment receives a kind by account and amount: a payment on 3220 is a Class 2 contribution of the year; a payment on 3210 is provisional tax of the year when it equals an instalment of the year, provisional tax of the preceding year when it equals an instalment of that year, and otherwise the settlement of the preceding year. The kind of a row of a saved record can be changed; a row without a kind, or with the kind Other, is not counted, and the reports say how many there are. The reports of a year read the payments for it from its own record and from the record of the following year.
- **Report "Tax Payments Malta"**: filters Company, Year and an as-of date. For the Malta Taxpayer listing the company, all payments falling due in the year by due date: the balance of the preceding year's tax on 30 June, the three provisional tax instalments and the three Class 2 periods of each self-occupied person, with the amount due, paid, open and the addition on late parts.
- **Report "Income Tax Computation Malta"**: the computation in the order of the return of income, in whole euro: chargeable income, for a married couple the separate and the joint computation and the lower tax charged, the rebate for certain income brackets up to basis year 2024, tax credits, tax at source, provisional tax paid and the balance due on 30 June of the year of assessment.
- **Report "Provisional Tax Malta"**: the benchmark from the record of the basis year two years earlier (the tax as filed, else as computed), the instalments of 20%, 30% and 50% due on 30 April, 31 August and 21 December, the limit of a P.T. Reduction Form, the payments applied in the order of the instalments, and the additional tax on late parts.
- **Report "Social Security Contributions Malta"**: per self-occupied person the weekly Class 2 rate from the net profit of the preceding year (categories SA, SB and SC by year of birth), the Mondays of the three four-month periods, the payments, and the addition on late parts. The first calendar year of an activity is charged at the rate SA. A person in insurable employment is marked on the record and left out.
- **Not covered**: the final tax on rental income, the tax on part-time work, the pension exemption and rebate, non-residents, the minimum tax of non-domiciled individuals, directors' fees of a spouse, the relief of double taxation, the amounts of personal deductions and tax credits, Class 2 contributions of farmers, the pro-rata option, Class 2 arrears paid in a later year at the rate of that year, and a change of the tax status during a year.

The rules are held in `malta_compliance/tax/rules.py` with their periods of validity, their source and its status: law, MTCA table without a Legal Notice, MTCA return guide, or announced in a Budget speech. The reports name the source of every table used. The computations import no Frappe and are tested without a site.

### Law check and tests

`tools/law_check.py` compares the consolidated texts on legislation.mt behind both rule registers with `malta_compliance/assets/law_versions.json`; the workflow `.github/workflows/law-check.yml` runs it monthly and opens an issue on a change. The Class 2 tables of MTCA and the Budget speeches are reviewed by hand once a year.

Tests, on a test site with ERPNext and the setup wizard completed:

```bash
bench --site <test site> run-tests --module malta_compliance.tests.test_capital_allowances
bench --site <test site> run-tests --module malta_compliance.tests.test_tax_rules
bench --site <test site> run-tests --module malta_compliance.tests.test_tax_year
bench --site <test site> run-tests --module malta_compliance.tests.test_desk
```

`test_tax_rules` also runs without a site: `python -m unittest malta_compliance.tests.test_tax_rules`.

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
