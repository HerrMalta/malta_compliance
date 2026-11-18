"""Tax result of the disposal of an asset under ITA art. 24, and the adjustment entry that brings ERPNext's disposal
result to it. ERPNext posts G = proceeds - value after depreciation on the company's disposal account (6200). The
balancing statement uses the capped cost and proceeds apportioned by the same ratio (S.L. 123.07 rule 3(1); IRD guide,
TRA 04), limits a balancing charge to the allowances given (art. 24(2) proviso (i)) and is reduced by the business
share (proviso (ii)). The private share of G goes to Drawings, the rest of the difference to account 3240.
Intellectual property (art. 5) and assets without any allowance (rule 7(b), art. 24(1)) keep no result on 6200.
"""

from dataclasses import dataclass

import frappe
from frappe import _
from frappe.utils import flt, getdate

from malta_compliance.assets import allowance
from malta_compliance.assets.allowance import INTELLECTUAL_PROPERTY
from malta_compliance.assets.depreciation import adjustment_fields, booked_allowances, cancel_adjustments
from malta_compliance.setup.vat import account

DRAWINGS = "3200"
NON_DEDUCTIBLE = "3240"


@dataclass
class Statement:
	"""Balancing statement of one disposal. Items (i) to (iii) on the capped basis; result before the business share
	(positive: balancing charge); tax_result: amount remaining in the profit (positive: charge)."""

	cost: float
	allowances: float
	proceeds: float
	capped_cost: float
	capped_allowances: float
	apportioned_proceeds: float
	result: float
	tax_result: float
	private: float
	non_deductible: float
	gain: float
	applies: bool


def statement(asset, proceeds: float, value_after: float, date) -> Statement:
	"""Balancing statement for a disposal on date at proceeds of an asset with the given value after depreciation.
	Item (ii) counts each allowance on the cap of its own year, as allowed; (i) and (iii) use the cap of the year of
	disposal."""
	total = allowance.cost(asset)
	allowances_booked = flt(total - flt(value_after), 2)
	gain = flt(flt(proceeds) - flt(value_after), 2)
	r = allowance.cap_ratio(asset, date)
	rows = booked_allowances(asset)
	private_share = business_share(asset, rows)
	applies = allowance.asset_rule(asset) != INTELLECTUAL_PROPERTY and allowances_booked > 0
	capped_cost, apportioned = total * r, flt(proceeds) * r
	capped_allowances = sum(amount * allowance.cap_ratio(asset, d) for d, amount in rows)
	result = capped_allowances + apportioned - capped_cost
	if result > capped_allowances:
		result = capped_allowances
	tax_result = flt(result * private_share, 2) if applies else 0.0
	private = flt((1 - private_share) * gain, 2)
	return Statement(
		cost=total,
		allowances=allowances_booked,
		proceeds=flt(proceeds),
		capped_cost=flt(capped_cost, 2),
		capped_allowances=flt(capped_allowances, 2),
		apportioned_proceeds=flt(apportioned, 2),
		result=flt(result, 2),
		tax_result=tax_result,
		private=private,
		non_deductible=flt(gain - tax_result - private, 2),
		gain=gain,
		applies=applies,
	)


def business_share(asset, rows: list[tuple]) -> float:
	"""Business share of the allowances booked, weighted by amount (art. 24(2) proviso (ii)); the current share when
	none were booked."""
	total = sum(amount for _date, amount in rows)
	if not total:
		return allowance.business_use(asset, getdate())
	return sum(allowance.business_use(asset, d) * amount for d, amount in rows) / total


def post_adjustment(
	asset_name: str, voucher, proceeds: float, value_after: float, withdrawal: float = 0
) -> str | None:
	"""Submits the Journal Entry moving the difference between ERPNext's result and the tax result off 6200; returns
	its name, or None when nothing differs. withdrawal: disposal value of a scrapped asset, booked against Drawings."""
	asset = frappe.get_doc("Asset", asset_name)
	result = statement(asset, proceeds, value_after, voucher.posting_date)
	company = asset.company
	disposal_account = frappe.get_cached_value("Company", company, "disposal_account")
	cost_center = asset.cost_center or frappe.get_cached_value("Company", company, "depreciation_cost_center")
	credit_disposal = flt(withdrawal - (result.gain - result.tax_result), 2)
	credit_drawings = flt(result.private - withdrawal, 2)
	credit_non_deductible = flt(-(credit_disposal + credit_drawings), 2)
	rows = []
	for account_name, amount in (
		(disposal_account, credit_disposal),
		(account(company, DRAWINGS), credit_drawings),
		(account(company, NON_DEDUCTIBLE), credit_non_deductible),
	):
		if not amount:
			continue
		row = {"account": account_name, "cost_center": cost_center}
		row["credit_in_account_currency" if amount > 0 else "debit_in_account_currency"] = abs(amount)
		rows.append(row)
	if not rows:
		return None
	je = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": company,
			"posting_date": voucher.posting_date,
			"accounts": rows,
			"user_remark": _(
				"Capital allowance adjustment of the disposal of {0}: balancing result {1}, private share {2}, "
				"non-deductible {3} (ITA art. 24)"
			).format(asset.name, result.tax_result, result.private, result.non_deductible),
			**adjustment_fields(voucher.doctype, voucher.name, asset.name),
		}
	)
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	return je.name


def on_sales_invoice_submit(doc, method=None):
	for item in doc.get("items"):
		if not (
			item.is_fixed_asset
			and item.asset
			and allowance.asset_rule(frappe.get_cached_doc("Asset", item.asset))
		):
			continue
		if doc.is_return:
			cancel_adjustments("Sales Invoice", doc.return_against, item.asset)
		else:
			post_adjustment(item.asset, doc, item.base_net_amount, item.asset_value_after_depreciation)


def on_sales_invoice_cancel(doc, method=None):
	cancel_adjustments(doc.doctype, doc.name)
	if not doc.is_return:
		return
	original = frappe.get_doc("Sales Invoice", doc.return_against)
	for item in original.get("items"):
		if (
			item.is_fixed_asset
			and item.asset
			and allowance.asset_rule(frappe.get_cached_doc("Asset", item.asset))
		):
			post_adjustment(item.asset, original, item.base_net_amount, item.asset_value_after_depreciation)


def on_scrap_entry_submit(doc) -> None:
	"""Scrap entry of ERPNext ("Asset Disposal"): the disposal value on the asset is the proceeds and a withdrawal."""
	assets = {
		row.reference_name for row in doc.accounts if row.reference_type == "Asset" and row.reference_name
	}
	for name in assets:
		asset = frappe.get_doc("Asset", name)
		if not allowance.asset_rule(asset):
			continue
		gross = sum(
			flt(r.credit)
			for r in doc.accounts
			if r.reference_name == name and r.credit and is_fixed_asset_account(r.account)
		)
		accumulated = sum(
			flt(r.debit)
			for r in doc.accounts
			if r.reference_name == name and r.debit and is_accumulated_account(r.account)
		)
		value_after = gross - accumulated
		disposal_value = flt(asset.mc_disposal_value)
		post_adjustment(name, doc, disposal_value, value_after, withdrawal=disposal_value)


def is_fixed_asset_account(name: str) -> bool:
	return frappe.get_cached_value("Account", name, "account_type") == "Fixed Asset"


def is_accumulated_account(name: str) -> bool:
	return frappe.get_cached_value("Account", name, "account_type") == "Accumulated Depreciation"
