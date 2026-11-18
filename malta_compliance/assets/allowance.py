"""Terms of an asset under the Maltese capital allowance rules: the rule of its category, the number of years and rates
resolved from the rule register, the cost cap and the deductible share per year. Values keyed to acquisition or
first use are frozen on the asset (mc_* fields) while it is a draft and read from there once it is submitted.
"""

from dataclasses import dataclass

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.utils import flt, getdate

from malta_compliance.assets import rules
from malta_compliance.setup.capital_allowances import (
	INDUSTRIAL_BUILDING,
	INTELLECTUAL_PROPERTY,
	WEAR_AND_TEAR,
	building_years,
)


@dataclass
class Terms:
	"""Resolved terms of one asset; years is the number of yearly rows of its schedule."""

	rule: str
	years: int
	minimum_years: int
	annual_rate: float
	initial_rate: float
	cap_applies: bool
	versions: list[str]


def category_rule(asset_category: str | None) -> str | None:
	if not asset_category:
		return None
	return frappe.get_cached_value("Asset Category", asset_category, "mc_allowance_rule") or None


def asset_rule(asset) -> str | None:
	return category_rule(asset.get("asset_category"))


def cost(asset) -> float:
	return flt(asset.net_purchase_amount) + flt(asset.get("additional_asset_cost"))


def resolve_terms(asset) -> Terms:
	"""Terms from the rule register for the asset's dates and options; raises a validation error outside the register."""
	rule = asset_rule(asset)
	first_use = getdate(asset.available_for_use_date)
	acquired = getdate(asset.purchase_date or asset.available_for_use_date)
	versions = []
	try:
		if rule == WEAR_AND_TEAR:
			item = frappe.get_cached_value("Asset Category", asset.asset_category, "mc_schedule_item")
			minimum = rules.wear_and_tear_years(item, first_use, acquired)
			initial = rules.select(rules.PLANT_INITIAL_RATE, first_use)
			versions += [minimum.code, initial.code]
			annual_rate, initial_rate, minimum_years = 0.0, initial.value, int(minimum.value)
		elif rule == INDUSTRIAL_BUILDING:
			annual = rules.select(rules.BUILDING_ANNUAL_RATE, first_use)
			versions.append(annual.code)
			initial_rate = 0.0
			if not asset.get("mc_no_initial_allowance"):
				initial = rules.select(rules.BUILDING_INITIAL_RATE, first_use)
				versions.append(initial.code)
				initial_rate = initial.value
			annual_rate = annual.value
			minimum_years = building_years(bool(initial_rate), first_use)
		elif rule == INTELLECTUAL_PROPERTY:
			minimum = rules.select(rules.IP_MINIMUM_YEARS, first_use)
			versions.append(minimum.code)
			annual_rate, initial_rate, minimum_years = 0.0, 0.0, int(minimum.value)
			if asset.get("mc_ip_one_year"):
				one_year = rules.select(rules.IP_ONE_YEAR, first_use)
				versions.append(one_year.code)
		else:
			frappe.throw(_("Asset Category {0} has no Maltese allowance rule").format(asset.asset_category))
	except rules.NotCovered as e:
		frappe.throw(
			_(
				"The Maltese capital allowance rules of this app do not cover this asset ({0}). An asset first used "
				"before 2001 is entered as an existing asset with its written-down value."
			).format(e),
			title=_("Date not covered"),
		)
	years = minimum_years
	if rule == INTELLECTUAL_PROPERTY and asset.get("mc_ip_one_year"):
		years = 1
	return Terms(rule, years, minimum_years, annual_rate, initial_rate, cap_applies(asset), versions)


def cap_applies(asset) -> bool:
	"""The vehicle cost cap applies: category with the cap and the asset not marked as outside rule 3(4)."""
	return bool(
		asset_rule(asset) == WEAR_AND_TEAR
		and frappe.get_cached_value("Asset Category", asset.asset_category, "mc_vehicle_cost_cap")
		and not asset.get("mc_cap_exempt")
	)


def frozen_terms(asset) -> Terms:
	"""Terms of a submitted asset as frozen on it; a draft resolves them."""
	if asset.docstatus == 0:
		return resolve_terms(asset)
	rule = asset_rule(asset)
	fb = asset.finance_books[0] if asset.get("finance_books") else None
	years = int(fb.total_number_of_depreciations) if fb else 0
	return Terms(
		rule,
		years,
		years,
		flt(asset.get("mc_annual_rate")),
		flt(asset.get("mc_initial_rate")),
		cap_applies(asset),
		(asset.get("mc_rule_version") or "").split(),
	)


def fiscal_year_name(date, company: str) -> str | None:
	fy = get_fiscal_year(date, company=company, as_dict=True, raise_on_missing=False)
	return fy.name if fy else None


def business_use(asset, date) -> float:
	"""Business share (0 to 1) of the fiscal year containing date."""
	year = fiscal_year_name(date, asset.company)
	for row in asset.get("mc_business_use_years") or []:
		if row.fiscal_year == year:
			return flt(row.business_use) / 100
	share = asset.get("mc_business_use")
	return (100 if share is None else flt(share)) / 100


def cap_ratio(asset, date) -> float:
	"""Capped cost / cost for a claim of the basis year containing date; 1 without cap or below it (S.L. 123.07
	rule 3(1))."""
	if not cap_applies(asset):
		return 1.0
	cap = rules.select(rules.VEHICLE_COST_CAP, getdate(date)).value
	total = cost(asset)
	return 1.0 if total <= cap else cap / total


def deductible_share(asset, date) -> tuple[float, float, float]:
	"""(f, p, r): deductible share f = p x r of an allowance booked on date, with business use p and cap ratio r."""
	p = business_use(asset, date)
	r = cap_ratio(asset, date)
	return p * r, p, r


def annual_amount(asset, terms: Terms, year_index: int, years: int) -> float:
	"""Allowance of the year with the given index from first use (0 = year of first use), before private use and cap.
	years: number of yearly rows of the finance book, at least the minimum."""
	total = cost(asset)
	if terms.rule == INDUSTRIAL_BUILDING:
		rate = terms.annual_rate + (terms.initial_rate if year_index == 0 else 0)
		return total * rate / 100
	return total / years
