"""Document events for assets of a category with a Maltese allowance rule: finance book settings, frozen rule values,
opening values of existing assets, and the rejection of operations the rules do not provide for. Assets of other
categories are not touched.
"""

import frappe
from erpnext.accounts.utils import get_fiscal_year
from erpnext.assets.doctype.asset.asset import get_item_details
from frappe import _
from frappe.utils import add_years, cint, flt, getdate

from malta_compliance.assets import allowance
from malta_compliance.setup.capital_allowances import (
	INDUSTRIAL_BUILDING,
	INTELLECTUAL_PROPERTY,
	WEAR_AND_TEAR,
)


def _category(doc) -> str | None:
	return doc.get("asset_category") or (
		frappe.get_cached_value("Item", doc.item_code, "asset_category") if doc.get("item_code") else None
	)


def asset_before_validate(doc, method=None):
	"""Sets the options and opening values ERPNext validates in Asset.validate."""
	if doc.docstatus != 0:
		return
	category = _category(doc)
	rule = allowance.category_rule(category)
	if not rule:
		return
	doc.asset_category = category
	doc.calculate_depreciation = 1
	if not doc.get("finance_books"):
		# Asset.validate requires the rows before its set_missing_values copies them from the category.
		doc.set("finance_books", get_item_details(doc.item_code, category, doc.net_purchase_amount))
	if doc.get("mc_business_use") is None:
		doc.mc_business_use = 100
	if doc.asset_type == "Existing Asset" and doc.available_for_use_date:
		set_opening_values(doc)


def set_opening_values(doc) -> None:
	"""Opening accumulated depreciation of an existing asset: the gross allowances of its opening years."""
	terms = allowance.resolve_terms(doc)
	years = _years(doc, terms)
	opening = cint(doc.opening_number_of_booked_depreciations)
	if opening >= years:
		frappe.throw(
			_("The opening years ({0}) must be fewer than the years of allowance ({1}).").format(
				opening, years
			)
		)
	derived = flt(sum(allowance.annual_amount(doc, terms, i, years) for i in range(opening)), 2)
	given = flt(doc.opening_accumulated_depreciation, 2)
	if given and given != derived:
		frappe.throw(
			_(
				"Opening Accumulated Depreciation must be {0}: the allowances of {1} years before private use and "
				"the vehicle cap."
			).format(derived, opening)
		)
	doc.opening_accumulated_depreciation = derived


def _years(doc, terms) -> int:
	"""Number of yearly rows: fixed for buildings and the one-year option, else the finance book value or the minimum."""
	if terms.rule == INDUSTRIAL_BUILDING or (
		terms.rule == INTELLECTUAL_PROPERTY and doc.get("mc_ip_one_year")
	):
		return terms.years
	rows = doc.get("finance_books") or []
	return (
		max(cint(rows[0].total_number_of_depreciations), terms.minimum_years) if rows else terms.minimum_years
	)


def asset_validate(doc, method=None):
	"""Runs after Asset.validate has copied the category's finance book rows and before on_update creates the
	schedule."""
	rule = allowance.asset_rule(doc)
	if not rule:
		return
	validate_business_use(doc)
	if doc.docstatus != 0:
		return
	if doc.get("split_from"):
		frappe.throw(_("Assets under the Maltese capital allowance rules cannot be split."))
	if rule != WEAR_AND_TEAR:
		doc.mc_cap_exempt = 0
	if rule != INDUSTRIAL_BUILDING:
		doc.mc_no_initial_allowance = 0
	if rule != INTELLECTUAL_PROPERTY:
		doc.mc_ip_one_year = 0
	terms = allowance.resolve_terms(doc)
	years = _years(doc, terms)
	if not doc.get("finance_books"):
		doc.append("finance_books", {})
	start = depreciation_start_date(doc)
	chosen_years = rule == WEAR_AND_TEAR or (rule == INTELLECTUAL_PROPERTY and not doc.get("mc_ip_one_year"))
	for row in doc.finance_books:
		if cint(row.get("increase_in_asset_life")):
			frappe.throw(_("The asset life of an asset under the Maltese rules cannot be increased."))
		given = cint(row.total_number_of_depreciations)
		if chosen_years and given and given < terms.minimum_years:
			frappe.throw(
				_("Row {0}: at least {1} years apply to this asset (minimum of the rule).").format(
					row.idx, terms.minimum_years
				)
			)
		row.update(
			{
				"depreciation_method": "Straight Line",
				"total_number_of_depreciations": years,
				"frequency_of_depreciation": 12,
				"daily_prorata_based": 0,
				"shift_based": 0,
				"salvage_value_percentage": 0,
				"expected_value_after_useful_life": 0,
				"depreciation_start_date": start,
			}
		)
	doc.mc_rule_version = " ".join(terms.versions)
	doc.mc_annual_rate = terms.annual_rate
	doc.mc_initial_rate = terms.initial_rate


def depreciation_start_date(doc):
	"""Last day of the fiscal year of first use, shifted by the opening years of an existing asset; 31 December where
	no Fiscal Year record exists (ITA art. 11(1))."""
	first_use = getdate(doc.available_for_use_date)
	fy = get_fiscal_year(first_use, company=doc.company, as_dict=True, raise_on_missing=False)
	year_end = getdate(fy.year_end_date) if fy else getdate(f"{first_use.year}-12-31")
	opening = cint(doc.opening_number_of_booked_depreciations) if doc.asset_type == "Existing Asset" else 0
	return add_years(year_end, opening)


def validate_business_use(doc) -> None:
	shares = [flt(doc.get("mc_business_use"))] + [
		flt(r.business_use) for r in doc.get("mc_business_use_years") or []
	]
	if any(s < 0 or s > 100 for s in shares):
		frappe.throw(_("Business use must lie between 0 and 100%."))
	years = [r.fiscal_year for r in doc.get("mc_business_use_years") or []]
	if len(years) != len(set(years)):
		frappe.throw(_("Each fiscal year may appear once in Business Use per Year."))


def asset_before_update_after_submit(doc, method=None):
	if allowance.asset_rule(doc):
		validate_business_use(doc)


def _reject(asset: str | None, operation: str) -> None:
	if asset and allowance.asset_rule(frappe.get_cached_doc("Asset", asset)):
		frappe.throw(
			_(
				"{0} is not available for asset {1}: under the Maltese capital allowance rules an improvement is a "
				"separate asset and the written-down value is not revalued."
			).format(operation, asset)
		)


def asset_value_adjustment_validate(doc, method=None):
	_reject(doc.asset, _("An Asset Value Adjustment"))


def asset_repair_validate(doc, method=None):
	if doc.get("capitalize_repair_cost") or cint(doc.get("increase_in_asset_life")):
		_reject(doc.asset, _("A capitalised repair"))


def asset_capitalization_validate(doc, method=None):
	_reject(doc.get("target_asset"), _("Asset Capitalization"))
	for row in doc.get("asset_items") or []:
		_reject(row.asset, _("Asset Capitalization"))
	if allowance.category_rule(
		frappe.get_cached_value("Item", doc.target_item_code, "asset_category")
		if doc.get("target_item_code")
		else None
	):
		frappe.throw(
			_(
				"Asset Capitalization into a category under the Maltese capital allowance rules is not available."
			)
		)
