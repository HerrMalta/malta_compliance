"""Capital allowance setup of a company: custom fields, the Asset Categories of the Maltese rules with their accounts,
one fixed-asset Item per category and a default Location. Idempotent: existing records are left as they are, nothing
is renamed or deleted. Legal basis: docs/capital-allowances.md; periods and rates come from assets/rules.py.

Custom fields are created first, because adding a column commits the open transaction in MariaDB.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils.nestedset import get_root_of

from malta_compliance.assets import rules

ITEM_GROUP = "Capital Allowance Assets"
ACCUMULATED_ACCOUNT = "1590"
WEAR_AND_TEAR = "Wear and Tear"
INDUSTRIAL_BUILDING = "Industrial Building"
INTELLECTUAL_PROPERTY = "Intellectual Property"
# Values of the asset field mc_building_condition; the initial deduction applies to new buildings only (IRD return
# workbook and guide: "only calculated on assets indicated as new").
NEW_BUILDING = "New building, not used before"
USED_BUILDING = "Used building"

# (category name, rule, Schedule item of S.L. 123.01 or 0, fixed asset account, expense account, vehicle cap).
CATEGORIES = (
	("CA 01 Computers and Electronic Equipment", WEAR_AND_TEAR, 1, "1510", "6100", 0),
	("CA 02 Computer Software", WEAR_AND_TEAR, 2, "1540", "6100", 0),
	("CA 03 Motor Vehicles", WEAR_AND_TEAR, 3, "1530", "6100", 1),
	("CA 04 Furniture, Fixtures, Fittings and Soft Furnishings", WEAR_AND_TEAR, 4, "1520", "6100", 0),
	("CA 05 Construction and Excavation Equipment", WEAR_AND_TEAR, 5, "1550", "6100", 0),
	("CA 06 Catering Equipment", WEAR_AND_TEAR, 6, "1550", "6100", 0),
	("CA 07 Aircraft Airframes, Engines, Overhauls and Interiors", WEAR_AND_TEAR, 7, "1550", "6100", 0),
	("CA 08 Ships and Vessels", WEAR_AND_TEAR, 8, "1550", "6100", 0),
	(
		"CA 09 Electrical and Plumbing Installations and Sanitary Fittings",
		WEAR_AND_TEAR,
		9,
		"1560",
		"6100",
		0,
	),
	("CA 10 Cable Infrastructure", WEAR_AND_TEAR, 10, "1550", "6100", 0),
	("CA 11 Pipeline Infrastructure", WEAR_AND_TEAR, 11, "1550", "6100", 0),
	("CA 12 Communication and Broadcasting Equipment", WEAR_AND_TEAR, 12, "1550", "6100", 0),
	("CA 13 Medical Equipment", WEAR_AND_TEAR, 13, "1550", "6100", 0),
	("CA 14 Lifts and Escalators", WEAR_AND_TEAR, 14, "1560", "6100", 0),
	("CA 15 Air-conditioners", WEAR_AND_TEAR, 15, "1560", "6100", 0),
	("CA 16 Water and Electricity Production Equipment", WEAR_AND_TEAR, 16, "1550", "6100", 0),
	("CA 17 Other Machinery", WEAR_AND_TEAR, 17, "1550", "6100", 0),
	("CA 18 Other Plant", WEAR_AND_TEAR, 18, "1550", "6100", 0),
	("CA IP Intellectual Property", INTELLECTUAL_PROPERTY, 0, "1570", "6110", 0),
	("CA IB Industrial Buildings and Structures", INDUSTRIAL_BUILDING, 0, "1580", "6120", 0),
	("CA Land", "", 0, "1585", "", 0),
)

LEGAL_REFERENCES = {
	INTELLECTUAL_PROPERTY: "ITA art. 14(1)(m)",
	INDUSTRIAL_BUILDING: "ITA art. 14(1)(f) and (j); S.L. 123.173",
	"": "No allowance (land, ITA art. 14(1)(f) proviso (iii)(b))",
}

CUSTOM_FIELDS = {
	"Asset Category": [
		{
			"fieldname": "mc_section",
			"label": "Malta Capital Allowances",
			"fieldtype": "Section Break",
			"insert_after": "non_depreciable_category",
		},
		{
			"fieldname": "mc_allowance_rule",
			"label": "Allowance Rule",
			"fieldtype": "Select",
			"options": f"\n{WEAR_AND_TEAR}\n{INDUSTRIAL_BUILDING}\n{INTELLECTUAL_PROPERTY}",
			"insert_after": "mc_section",
			"description": "Applies the Maltese capital allowance rules to the assets of this category",
		},
		{
			"fieldname": "mc_schedule_item",
			"label": "Schedule Item (S.L. 123.01)",
			"fieldtype": "Int",
			"insert_after": "mc_allowance_rule",
			"depends_on": f"eval:doc.mc_allowance_rule=='{WEAR_AND_TEAR}'",
		},
		{
			"fieldname": "mc_legal_reference",
			"label": "Legal Reference",
			"fieldtype": "Data",
			"read_only": 1,
			"insert_after": "mc_schedule_item",
		},
		{
			"fieldname": "mc_vehicle_cost_cap",
			"label": "Vehicle Cost Cap (S.L. 123.07 rule 3)",
			"fieldtype": "Check",
			"insert_after": "mc_legal_reference",
			"description": "Default for new assets of this category",
		},
	],
	"Asset": [
		{
			"fieldname": "mc_section",
			"label": "Malta Capital Allowances",
			"fieldtype": "Section Break",
			"insert_after": "finance_books",
			"collapsible": 1,
		},
		{
			"fieldname": "mc_business_use",
			"label": "Business Use (%)",
			"fieldtype": "Percent",
			"default": "100",
			"allow_on_submit": 1,
			"insert_after": "mc_section",
			"description": "Share of use in the production of the income (S.L. 123.01 rule 11) for years without a row below",
		},
		{
			"fieldname": "mc_business_use_years",
			"label": "Business Use per Year",
			"fieldtype": "Table",
			"options": "Malta Asset Business Use",
			"allow_on_submit": 1,
			"insert_after": "mc_business_use",
		},
		{
			"fieldname": "mc_cap_exempt",
			"label": "Vehicle Outside the Cost Cap",
			"fieldtype": "Check",
			"insert_after": "mc_business_use_years",
			"description": "Vehicle of a category with the cost cap that falls outside S.L. 123.07 rule 3(4): not commonly used as a private vehicle, hire or carriage of the public, driving instruction",
		},
		{
			"fieldname": "mc_building_condition",
			"label": "Building Condition (Industrial Building)",
			"fieldtype": "Select",
			"options": f"\n{NEW_BUILDING}\n{USED_BUILDING}",
			"insert_after": "mc_cap_exempt",
			"description": "Required for industrial buildings and structures; the initial deduction of ITA art. 14(1)(j) applies to a new building only",
		},
		{
			"fieldname": "mc_ip_one_year",
			"label": "Deduct in One Year (Intellectual Property)",
			"fieldtype": "Check",
			"insert_after": "mc_building_condition",
			"description": "ITA art. 14(1)(m) second proviso; the part above one third is deductible only against income produced by the asset",
		},
		{
			"fieldname": "mc_disposal_value",
			"label": "Disposal Value",
			"fieldtype": "Currency",
			"options": "Company:company:default_currency",
			"allow_on_submit": 1,
			"insert_after": "mc_ip_one_year",
			"description": "Market value when the asset is scrapped or taken into private use (ITA art. 24(7)(d))",
		},
		{
			"fieldname": "mc_column",
			"fieldtype": "Column Break",
			"insert_after": "mc_disposal_value",
		},
		{
			"fieldname": "mc_rule_version",
			"label": "Rule Versions",
			"fieldtype": "Small Text",
			"read_only": 1,
			"insert_after": "mc_column",
		},
		{
			"fieldname": "mc_annual_rate",
			"label": "Annual Rate (%)",
			"fieldtype": "Percent",
			"read_only": 1,
			"insert_after": "mc_rule_version",
		},
		{
			"fieldname": "mc_initial_rate",
			"label": "Initial Rate (%)",
			"fieldtype": "Percent",
			"read_only": 1,
			"insert_after": "mc_annual_rate",
		},
	],
	"Journal Entry": [
		{
			"fieldname": "mc_adjustment_doctype",
			"label": "Capital Allowance Adjustment For (Type)",
			"fieldtype": "Link",
			"options": "DocType",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "user_remark",
		},
		{
			"fieldname": "mc_adjustment_for",
			"label": "Capital Allowance Adjustment For",
			"fieldtype": "Dynamic Link",
			"options": "mc_adjustment_doctype",
			"read_only": 1,
			"no_copy": 1,
			"search_index": 1,
			"insert_after": "mc_adjustment_doctype",
		},
		{
			"fieldname": "mc_asset",
			"label": "Capital Allowance Adjustment Asset",
			"fieldtype": "Link",
			"options": "Asset",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "mc_adjustment_for",
		},
	],
}


def ensure_custom_fields() -> None:
	create_custom_fields(CUSTOM_FIELDS, update=True)
	frappe.db.commit()


def after_install() -> None:
	ensure_custom_fields()


def setup_capital_allowances(company: str, create_fields: bool = True) -> dict:
	"""Creates the missing categories, their account rows for the company, the Items and a Location. Requires the
	accounts of chart_self_employed.json in the company (company.ensure_chart_accounts)."""
	if create_fields:
		ensure_custom_fields()
	categories = [ensure_category(company, row) for row in CATEGORIES]
	ensure_item_group()
	items = [ensure_item(name) for name, *_ in CATEGORIES]
	ensure_location(company)
	return {"categories": sum(categories), "items": sum(items)}


def account(company: str, number: str) -> str:
	name = frappe.db.get_value("Account", {"company": company, "account_number": number, "is_group": 0})
	if not name:
		frappe.throw(f"Account {number} missing in company {company}")
	return name


def finance_book_row(rule: str, item: int) -> dict:
	"""Default finance book row of a category: the current minimum period."""
	today = frappe.utils.getdate()
	if rule == WEAR_AND_TEAR:
		years = rules.wear_and_tear_years(item, today, today).value
	elif rule == INTELLECTUAL_PROPERTY:
		years = rules.select(rules.IP_MINIMUM_YEARS, today).value
	else:
		years = building_years(True, today)
	return {
		"depreciation_method": "Straight Line",
		"total_number_of_depreciations": int(years),
		"frequency_of_depreciation": 12,
		"daily_prorata_based": 0,
		"shift_based": 0,
		"salvage_value_percentage": 0,
	}


def building_years(initial_allowance: bool, first_use) -> int:
	"""Number of yearly rows that exhaust the cost: the first row carries the initial rate in addition."""
	annual = rules.select(rules.BUILDING_ANNUAL_RATE, first_use).value
	initial = rules.select(rules.BUILDING_INITIAL_RATE, first_use).value if initial_allowance else 0
	remaining = 100 - annual - initial
	return 1 + int(-(-remaining // annual))


def ensure_category(company: str, row: tuple) -> int:
	"""Creates the category or adds the company's account row; returns 1 when the category was created."""
	name, rule, item, fixed_asset, expense, cap = row
	if frappe.db.exists("Asset Category", name):
		doc = frappe.get_doc("Asset Category", name)
		if not any(a.company_name == company for a in doc.accounts):
			doc.append("accounts", category_accounts(company, fixed_asset, expense))
			doc.save(ignore_permissions=True)
		return 0
	doc = frappe.get_doc(
		{
			"doctype": "Asset Category",
			"asset_category_name": name,
			"non_depreciable_category": 0 if rule else 1,
			"enable_cwip_accounting": 0,
			"mc_allowance_rule": rule,
			"mc_schedule_item": item,
			"mc_legal_reference": f"S.L. 123.01 Schedule item {item}" if item else LEGAL_REFERENCES[rule],
			"mc_vehicle_cost_cap": cap,
			"finance_books": [finance_book_row(rule, item)] if rule else [],
			"accounts": [category_accounts(company, fixed_asset, expense)],
		}
	)
	doc.insert(ignore_permissions=True)
	return 1


def category_accounts(company: str, fixed_asset: str, expense: str) -> dict:
	row = {"company_name": company, "fixed_asset_account": account(company, fixed_asset)}
	if expense:
		row["accumulated_depreciation_account"] = account(company, ACCUMULATED_ACCOUNT)
		row["depreciation_expense_account"] = account(company, expense)
	return row


def ensure_item_group() -> None:
	if not frappe.db.exists("Item Group", ITEM_GROUP):
		parent = get_root_of("Item Group")
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": ITEM_GROUP,
				"parent_item_group": parent,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)


def ensure_item(category: str) -> int:
	if frappe.db.exists("Item", category):
		return 0
	uom = "Nos" if frappe.db.exists("UOM", "Nos") else frappe.db.get_value("UOM", {})
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": category,
			"item_name": category,
			"item_group": ITEM_GROUP,
			"stock_uom": uom,
			"is_stock_item": 0,
			"is_fixed_asset": 1,
			"asset_category": category,
			"include_item_in_manufacturing": 0,
			"is_sales_item": 1,
			"is_purchase_item": 1,
		}
	).insert(ignore_permissions=True)
	return 1


def ensure_location(company: str) -> None:
	if not frappe.db.exists("Location", company):
		frappe.get_doc({"doctype": "Location", "location_name": company}).insert(ignore_permissions=True)
