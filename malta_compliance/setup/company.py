"""Sets up an ERPNext company for a self-employed individual in Malta: chart of accounts from
chart_self_employed.json, bank accounts, company address, fiscal years, default accounts, VAT setup by registration
article with the record Malta VAT Registration (vat.py), capital allowance categories (capital_allowances.py), a
service item and the field for the original invoice number on Sales Invoice. Idempotent: an existing company keeps its accounts and receives the accounts of the
chart it lacks; missing parts are added. Personal data comes in as arguments only.

Run as Administrator, for example:
    bench --site <site> execute malta_compliance.setup.company.setup_company --kwargs "{...}"
"""

import json
import os

import frappe
from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import create_charts
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from malta_compliance.setup import capital_allowances, vat
from malta_compliance.setup.vat import account, ensure_registration, setup_vat

CHART_FILE = os.path.join(os.path.dirname(__file__), "chart_self_employed.json")
# Keys of a chart node that are account properties, not child accounts.
CHART_PROPERTIES = {"account_number", "account_type", "is_group", "root_type", "account_currency", "tax_rate"}
BANK_GROUP = "1100"
SERVICE_ITEM = "Software Development"

# Company field and account number in the chart.
DEFAULT_ACCOUNTS = {
	"default_cash_account": "1150",
	"default_receivable_account": "1210",
	"default_payable_account": "2110",
	"default_income_account": "4100",
	"default_expense_account": "5990",
	"round_off_account": "5995",
	"write_off_account": "5980",
	"exchange_gain_loss_account": "5610",
	"unrealized_exchange_gain_loss_account": "5610",
	"accumulated_depreciation_account": "1590",
	"depreciation_expense_account": "6100",
	"disposal_account": "6200",
	"asset_received_but_not_billed": "2310",
}

CUSTOM_FIELDS = {
	"Sales Invoice": [
		{
			"fieldname": "mc_original_invoice_no",
			"label": "Original Invoice No",
			"fieldtype": "Data",
			"insert_after": "customer",
			"in_standard_filter": 1,
			"search_index": 1,
			"no_copy": 1,
			"description": "Number of the invoice issued outside ERPNext",
		}
	]
}


def setup_company(
	company_name: str,
	abbr: str,
	vat_article: int,
	tax_id: str | None = None,
	email: str | None = None,
	phone_no: str | None = None,
	address: dict | None = None,
	banks: list | None = None,
	fiscal_years: list | None = None,
	default_company: bool = False,
	vat_registered_from: str | None = None,
	activity: str | None = None,
	article_12_number: str | None = None,
	article_12_from: str | None = None,
) -> dict:
	"""address: Address fields (address_line1, address_line2, city, pincode). banks: dicts with bank, swift_number,
	account_name, account_number (4 digits in the 1100 group) and iban. fiscal_years: calendar years. tax_id: the
	registration number under the article, vat_registered_from its effective date. activity: the category of the
	Malta VAT Registration. article_12_number or article_12_from: a registration under Article 12 beside one under
	Article 11."""
	frappe.only_for("System Manager")
	vat_article = int(vat_article)
	if vat_article not in (10, 11):
		frappe.throw("vat_article must be 10 or 11")
	article_12 = bool(article_12_number or article_12_from)
	if article_12 and vat_article != 11:
		frappe.throw("A registration under Article 12 is set up beside vat_article 11 only")

	# Adding the column commits implicitly in MariaDB, so it runs before the company is created; everything after
	# it is one transaction.
	create_custom_fields(CUSTOM_FIELDS, update=True)
	capital_allowances.ensure_custom_fields()
	vat.ensure_custom_fields()
	frappe.db.commit()
	for year in fiscal_years or ():
		ensure_fiscal_year(int(year))
	company, created = ensure_company(company_name, abbr, tax_id, email, phone_no)
	accounts_added = [] if created else ensure_chart_accounts(company.name)
	bank_accounts = [ensure_bank(company.name, bank) for bank in banks or ()]
	set_defaults(company.name, bank_accounts[0] if bank_accounts else None)
	if address:
		ensure_address(company.name, address)
	templates = setup_vat(company.name, vat_article, article_12)
	registered = ensure_registration(
		company.name, vat_article, tax_id, vat_registered_from, activity, article_12_number, article_12_from
	)
	allowances = capital_allowances.setup_capital_allowances(company.name, create_fields=False)
	ensure_service_item(company.name)
	if default_company:
		frappe.db.set_single_value("Global Defaults", "default_company", company.name)
		frappe.defaults.set_global_default("company", company.name)
	frappe.db.commit()
	return {
		"company": company.name,
		"created": created,
		"accounts": frappe.db.count("Account", {"company": company.name}),
		"bank_accounts": bank_accounts,
		"templates_created": templates,
		"vat_registration_created": registered,
		"accounts_added": accounts_added,
		"capital_allowances": allowances,
	}


def ensure_fiscal_year(year: int) -> None:
	if not frappe.db.exists("Fiscal Year", str(year)):
		frappe.get_doc(
			{
				"doctype": "Fiscal Year",
				"year": str(year),
				"year_start_date": f"{year}-01-01",
				"year_end_date": f"{year}-12-31",
			}
		).insert(ignore_permissions=True)


def ensure_company(company_name, abbr, tax_id, email, phone_no):
	if frappe.db.exists("Company", company_name):
		return frappe.get_doc("Company", company_name), False
	# Without the flag, inserting a company creates the standard chart, warehouses and the country's tax template.
	frappe.local.flags.ignore_chart_of_accounts = True
	try:
		company = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": company_name,
				"abbr": abbr,
				"default_currency": "EUR",
				"country": "Malta",
				"create_chart_of_accounts_based_on": "Standard Template",
				"chart_of_accounts": "Standard",
				"enable_perpetual_inventory": 0,
				"tax_id": tax_id,
				"email": email,
				"phone_no": phone_no,
			}
		)
		company.insert(ignore_permissions=True)
	finally:
		frappe.local.flags.ignore_chart_of_accounts = False
	frappe.local.flags.ignore_root_company_validation = True
	try:
		with open(CHART_FILE) as f:
			create_charts(company.name, custom_chart=json.load(f))
	finally:
		frappe.local.flags.ignore_root_company_validation = False
	return frappe.get_doc("Company", company.name), True


def ensure_chart_accounts(company: str) -> list[str]:
	"""Adds the accounts of chart_self_employed.json missing in an existing company below the group of the parent
	node, found by account number (by name for the root accounts); returns the names of the accounts created."""
	with open(CHART_FILE) as f:
		chart = json.load(f)
	created = []

	def walk(nodes: dict, parent: str | None, root_type: str | None) -> None:
		for name, node in nodes.items():
			if name in CHART_PROPERTIES or not isinstance(node, dict):
				continue
			children = {k: v for k, v in node.items() if k not in CHART_PROPERTIES and isinstance(v, dict)}
			is_group = 1 if children or node.get("is_group") else 0
			number = node.get("account_number")
			node_root_type = node.get("root_type", root_type)
			filters = (
				{"company": company, "account_number": number}
				if number
				else {"company": company, "account_name": name, "is_group": 1, "root_type": node_root_type}
			)
			existing = frappe.db.get_value("Account", filters)
			if not existing:
				if not parent:
					frappe.throw(f"Root account {name} missing in company {company}")
				existing = (
					frappe.get_doc(
						{
							"doctype": "Account",
							"company": company,
							"account_name": name,
							"account_number": number,
							"parent_account": parent,
							"is_group": is_group,
							"account_type": node.get("account_type"),
						}
					)
					.insert(ignore_permissions=True)
					.name
				)
				created.append(existing)
			walk(children, existing, node_root_type)

	walk(chart, None, None)
	return created


def ensure_bank(company: str, bank: dict) -> str:
	"""Creates the bank, its ledger account below the bank group and the company's Bank Account; returns the ledger
	account."""
	if not frappe.db.exists("Bank", bank["bank"]):
		frappe.get_doc(
			{"doctype": "Bank", "bank_name": bank["bank"], "swift_number": bank.get("swift_number")}
		).insert(ignore_permissions=True)
	ledger = frappe.db.get_value("Account", {"company": company, "account_number": bank["account_number"]})
	if not ledger:
		ledger = (
			frappe.get_doc(
				{
					"doctype": "Account",
					"company": company,
					"account_name": bank["account_name"],
					"account_number": bank["account_number"],
					"parent_account": account_group(company, BANK_GROUP),
					"account_type": "Bank",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
	if not frappe.db.exists("Bank Account", {"account": ledger}):
		frappe.get_doc(
			{
				"doctype": "Bank Account",
				"account_name": bank["account_name"],
				"bank": bank["bank"],
				"account": ledger,
				"company": company,
				"is_company_account": 1,
				"is_default": int(
					not frappe.db.exists("Bank Account", {"company": company, "is_default": 1})
				),
				"iban": bank.get("iban"),
			}
		).insert(ignore_permissions=True)
	return ledger


def account_group(company: str, number: str) -> str:
	return frappe.db.get_value("Account", {"company": company, "account_number": number, "is_group": 1})


def set_defaults(company_name: str, bank_account: str | None) -> None:
	company = frappe.get_doc("Company", company_name)
	updates = {
		field: account(company.name, number)
		for field, number in DEFAULT_ACCOUNTS.items()
		if not company.get(field)
	}
	if bank_account and not company.default_bank_account:
		updates["default_bank_account"] = bank_account
	cost_center = frappe.db.get_value("Cost Center", {"company": company.name, "is_group": 0})
	for field in ("cost_center", "round_off_cost_center", "depreciation_cost_center"):
		if not company.get(field):
			updates[field] = cost_center
	if updates:
		company.update(updates)
		company.save(ignore_permissions=True)


def ensure_address(company: str, address: dict) -> None:
	name = frappe.db.get_value(
		"Dynamic Link", {"parenttype": "Address", "link_doctype": "Company", "link_name": company}, "parent"
	)
	doc = frappe.get_doc("Address", name) if name else frappe.new_doc("Address")
	doc.update(
		{
			"address_title": company,
			"address_type": "Billing",
			"country": "Malta",
			"is_your_company_address": 1,
			"is_primary_address": 1,
			**address,
		}
	)
	if not name:
		doc.append("links", {"link_doctype": "Company", "link_name": company})
	doc.save(ignore_permissions=True)


def ensure_service_item(company: str) -> None:
	item = (
		frappe.get_doc("Item", SERVICE_ITEM)
		if frappe.db.exists("Item", SERVICE_ITEM)
		else frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": SERVICE_ITEM,
				"item_name": "Software development services",
				"item_group": "Services",
				"stock_uom": "Hour",
				"is_stock_item": 0,
				"include_item_in_manufacturing": 0,
				"is_sales_item": 1,
				"is_purchase_item": 0,
			}
		)
	)
	if not any(row.company == company for row in item.get("item_defaults", [])):
		item.append("item_defaults", {"company": company, "income_account": account(company, "4100")})
	item.save(ignore_permissions=True)
