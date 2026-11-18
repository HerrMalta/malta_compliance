"""Capital allowances of a company for one fiscal year: one row per asset of a Maltese category with the allowance of
the year, its deductible part after private use and the vehicle cap, the tax written-down value on the capped cost,
and the balancing statement of a disposal (ITA art. 24); for intellectual property the figures of the capital gain
instead (ITA art. 5). Totals per line of the MTCA profit and loss form: 22 intellectual property, 23 industrial
buildings, 24 wear and tear. Unabsorbed allowances (art. 14(1)(f) proviso (ii)) and the part (b) of the one-year
option above the qualifying income are computed outside the app; the report shows the check value for the latter.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from malta_compliance.assets import allowance, balancing, rules
from malta_compliance.assets.depreciation import booked_allowances
from malta_compliance.setup.capital_allowances import (
	INDUSTRIAL_BUILDING,
	INTELLECTUAL_PROPERTY,
	WEAR_AND_TEAR,
)
from malta_compliance.setup.vat import account

FORM_LINES = {INTELLECTUAL_PROPERTY: "22", INDUSTRIAL_BUILDING: "23", WEAR_AND_TEAR: "24"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	fy = frappe.get_cached_doc("Fiscal Year", filters.fiscal_year)
	start, end = getdate(fy.year_start_date), getdate(fy.year_end_date)
	data, totals, ip_parts = [], {}, [0.0, 0.0]
	for name in malta_assets(filters.company, start, end):
		asset = frappe.get_doc("Asset", name)
		row = asset_row(asset, start, end)
		data.append(row)
		line = FORM_LINES[row["rule"]]
		totals[line] = totals.get(line, 0) + row["deductible"]
		totals["balancing"] = totals.get("balancing", 0) + flt(row.get("balancing"))
		ip_parts[0] += flt(row.get("ip_part_a"))
		ip_parts[1] += flt(row.get("ip_part_b"))
	message = summary_message(filters.company, start, end, ip_parts)
	return columns(), data, message, None, report_summary(totals)


def malta_assets(company: str, start, end) -> list[str]:
	categories = frappe.get_all("Asset Category", filters={"mc_allowance_rule": ["is", "set"]}, pluck="name")
	if not categories:
		return []
	return frappe.get_all(
		"Asset",
		filters={
			"company": company,
			"docstatus": 1,
			"asset_category": ["in", categories],
			"available_for_use_date": ["<=", end],
		},
		or_filters=[["disposal_date", "is", "not set"], ["disposal_date", ">=", start]],
		order_by="asset_category, available_for_use_date",
		pluck="name",
	)


def asset_row(asset, start, end) -> dict:
	terms = allowance.frozen_terms(asset)
	total = allowance.cost(asset)
	r = allowance.cap_ratio(asset, end)
	rows = booked_allowances(asset) + scheduled_allowances(asset, end)
	year = [(d, a) for d, a in rows if start <= getdate(d) <= end]
	to_date = [(d, a) for d, a in rows if getdate(d) <= end]
	row = {
		"asset": asset.name,
		"asset_name": asset.asset_name,
		"asset_category": asset.asset_category,
		"rule": terms.rule,
		"legal_reference": frappe.get_cached_value(
			"Asset Category", asset.asset_category, "mc_legal_reference"
		),
		"first_use": asset.available_for_use_date,
		"cost": total,
		"allowance_base": flt(total * r, 2),
		"business_use": flt(allowance.business_use(asset, end) * 100, 2),
		"allowance": flt(sum(a for _d, a in year), 2),
		"deductible": flt(sum(a * allowance.deductible_share(asset, d)[0] for d, a in year), 2),
		"deductible_to_date": flt(sum(a * allowance.deductible_share(asset, d)[0] for d, a in to_date), 2),
		"written_down_value": flt(total * r - sum(a * allowance.cap_ratio(asset, d) for d, a in to_date), 2),
	}
	if (
		terms.rule == INTELLECTUAL_PROPERTY
		and asset.get("mc_ip_one_year")
		and start <= getdate(asset.available_for_use_date) <= end
	):
		minimum = rules.select(rules.IP_MINIMUM_YEARS, getdate(asset.available_for_use_date)).value
		row["ip_part_a"] = flt(total / minimum, 2)
		row["ip_part_b"] = flt(total - row["ip_part_a"], 2)
	if asset.disposal_date and start <= getdate(asset.disposal_date) <= end:
		row.update(disposal_columns(asset))
	return row


def scheduled_allowances(asset, end) -> list[tuple]:
	"""Rows of the active schedule up to end that are not yet booked."""
	schedule = frappe.get_all(
		"Asset Depreciation Schedule", filters={"asset": asset.name, "docstatus": 1}, pluck="name"
	)
	if not schedule:
		return []
	return [
		(r.schedule_date, flt(r.depreciation_amount))
		for r in frappe.get_all(
			"Depreciation Schedule",
			filters={
				"parent": ["in", schedule],
				"journal_entry": ["is", "not set"],
				"schedule_date": ["<=", end],
			},
			fields=["schedule_date", "depreciation_amount"],
		)
	]


def disposal_columns(asset) -> dict:
	proceeds, value_after = disposal_values(asset)
	if proceeds is None:
		return {}
	if allowance.asset_rule(asset) == INTELLECTUAL_PROPERTY:
		return capital_gain_columns(asset, proceeds, value_after)
	s = balancing.statement(asset, proceeds, value_after, asset.disposal_date)
	return {
		"capped_cost": s.capped_cost,
		"capped_allowances": s.capped_allowances,
		"proceeds": s.proceeds,
		"apportioned_proceeds": s.apportioned_proceeds,
		"balancing": s.tax_result,
		"disposal_note": ""
		if s.applies
		else _("Not in the balancing statement (art. 5 or no allowance given)"),
	}


def capital_gain_columns(asset, proceeds: float, value_after: float) -> dict:
	"""Transfer of intellectual property under ITA art. 5: the cost of acquisition excludes the deductions claimed under
	art. 14(1)(m) (S.L. 123.27 rules 3 and 4(2)); a loss is set off only against capital gains (art. 5(10)(b))."""
	total = allowance.cost(asset)
	claimed = flt(total - flt(value_after), 2)
	reduced_cost = flt(total - claimed, 2)
	gain = flt(flt(proceeds) - reduced_cost, 2)
	note = (
		_("Capital gain, ITA art. 5")
		if gain >= 0
		else _("Capital loss, carried forward against capital gains (ITA art. 5(10)(b))")
	)
	return {
		"proceeds": flt(proceeds),
		"deductions_claimed": claimed,
		"reduced_cost": reduced_cost,
		"capital_gain": gain,
		"disposal_note": note,
	}


def disposal_values(asset) -> tuple:
	"""(proceeds, value after depreciation) of the disposal of the asset, or (None, None)."""
	item = frappe.db.sql(
		"""select sii.base_net_amount, sii.asset_value_after_depreciation from `tabSales Invoice Item` sii
		join `tabSales Invoice` si on si.name = sii.parent
		where sii.asset = %s and si.docstatus = 1 and si.is_return = 0 order by si.posting_date desc limit 1""",
		asset.name,
	)
	if item:
		return flt(item[0][0]), flt(item[0][1])
	if asset.journal_entry_for_scrap:
		rows = frappe.get_all(
			"Journal Entry Account",
			filters={"parent": asset.journal_entry_for_scrap, "reference_name": asset.name},
			fields=["account", "debit", "credit"],
		)
		gross = sum(flt(r.credit) for r in rows if balancing.is_fixed_asset_account(r.account))
		accumulated = sum(flt(r.debit) for r in rows if balancing.is_accumulated_account(r.account))
		return flt(asset.mc_disposal_value), gross - accumulated
	return None, None


def summary_message(company: str, start, end, ip_parts: list) -> str:
	lines = []
	warning = rules.review_warning(end.year)
	if warning:
		lines.append(warning)
	if ip_parts[1]:
		profit = profit_before_ip(company, start, end)
		check = flt(profit - ip_parts[0], 2)
		above = flt(max(0, ip_parts[1] - check), 2)
		lines.append(
			_(
				"Intellectual property, one-year option: part (b) {0} is deductible only against the income produced "
				"by the property. Profit before account 6110 less part (a): {1}; part (b) above it: {2} (S.L. 123.07 "
				"rule 6, MTCA guidance note on art. 14(1)(m))."
			).format(ip_parts[1], check, above)
		)
	return "<br>".join(lines)


def profit_before_ip(company: str, start, end) -> float:
	ip_account = account(company, "6110")
	result = frappe.db.sql(
		"""select sum(gle.credit - gle.debit) from `tabGL Entry` gle join `tabAccount` acc on acc.name = gle.account
		where gle.company = %s and gle.is_cancelled = 0 and gle.posting_date between %s and %s
		and acc.root_type in ('Income', 'Expense') and gle.account != %s""",
		(company, start, end, ip_account),
	)
	return flt(result[0][0]) if result else 0.0


def report_summary(totals: dict) -> list[dict]:
	labels = {
		"24": _("Line 24, wear and tear"),
		"23": _("Line 23, industrial buildings"),
		"22": _("Line 22, intellectual property"),
		"balancing": _("Balancing allowances (-) and charges (+)"),
	}
	return [
		{"label": label, "value": flt(totals.get(key), 2), "datatype": "Currency", "indicator": "Blue"}
		for key, label in labels.items()
		if key in totals
	]


def columns() -> list[dict]:
	def col(fieldname, label, fieldtype="Currency", width=120, options=None):
		c = {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}
		if options:
			c["options"] = options
		return c

	return [
		col("asset", _("Asset"), "Link", 140, "Asset"),
		col("asset_name", _("Asset Name"), "Data", 160),
		col("asset_category", _("Category"), "Link", 200, "Asset Category"),
		col("legal_reference", _("Legal Reference"), "Data", 180),
		col("first_use", _("First Use"), "Date", 100),
		col("cost", _("Cost")),
		col("allowance_base", _("Allowance Base")),
		col("business_use", _("Business Use (%)"), "Percent", 90),
		col("allowance", _("Allowance of the Year")),
		col("deductible", _("Deductible")),
		col("deductible_to_date", _("Deductible to Date")),
		col("written_down_value", _("Tax Written-down Value")),
		col("ip_part_a", _("IP Part (a)")),
		col("ip_part_b", _("IP Part (b)")),
		col("capped_cost", _("(i) Cost")),
		col("capped_allowances", _("(ii) Allowances")),
		col("proceeds", _("Proceeds")),
		col("apportioned_proceeds", _("(iii) Proceeds Apportioned")),
		col("balancing", _("Balancing Result")),
		col("deductions_claimed", _("Deductions Claimed (IP)")),
		col("reduced_cost", _("Cost less Deductions (IP)")),
		col("capital_gain", _("Capital Gain or Loss (IP)")),
		col("disposal_note", _("Note"), "Data", 260),
	]
