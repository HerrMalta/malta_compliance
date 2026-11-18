"""Adjustment of ERPNext's depreciation entries of Maltese assets for private use and the vehicle cost cap (S.L. 123.01
rule 11, S.L. 123.07 rule 3). ERPNext's entry stays as it is, because ERPNext links it to the schedule row only while
its expense debit equals the scheduled amount. A second entry of type "Depreciation Entry", without asset reference,
moves the private share to Drawings (3200) and the capped excess to 3240, so the expense account keeps the
deductible amount. Adjustments are linked through mc_adjustment_doctype / mc_adjustment_for and cancelled with
their voucher; an adjustment alone cannot be cancelled while its voucher is submitted.
"""

import frappe
from frappe import _
from frappe.utils import add_years, cint, flt, getdate

from malta_compliance.assets import allowance, rules
from malta_compliance.setup.vat import account

DRAWINGS = "3200"
NON_DEDUCTIBLE = "3240"


def adjustment_fields(doctype: str, name: str, asset: str) -> dict:
	return {"mc_adjustment_doctype": doctype, "mc_adjustment_for": name, "mc_asset": asset}


def booked_allowances(asset) -> list[tuple]:
	"""(date, amount) of every allowance booked for the asset: the opening years of an existing asset, then the
	schedule rows with a Journal Entry."""
	rows = []
	opening = cint(asset.get("opening_number_of_booked_depreciations"))
	if opening and flt(asset.get("opening_accumulated_depreciation")):
		first_use = getdate(asset.available_for_use_date)
		terms = allowance.frozen_terms(asset)
		years = (
			cint(asset.finance_books[0].total_number_of_depreciations)
			if asset.get("finance_books")
			else terms.years
		)
		for i in range(opening):
			rows.append((add_years(first_use, i), allowance.annual_amount(asset, terms, i, years)))
	schedule = frappe.get_all(
		"Asset Depreciation Schedule", filters={"asset": asset.name, "docstatus": 1}, pluck="name"
	)
	if schedule:
		rows += [
			(r.schedule_date, flt(r.depreciation_amount))
			for r in frappe.get_all(
				"Depreciation Schedule",
				filters={"parent": ["in", schedule], "journal_entry": ["is", "set"]},
				fields=["schedule_date", "depreciation_amount", "journal_entry"],
				order_by="schedule_date",
			)
			if frappe.db.get_value("Journal Entry", r.journal_entry, "docstatus") == 1
		]
	return rows


def on_journal_entry_submit(doc, method=None):
	if doc.get("mc_adjustment_for"):
		return
	if doc.voucher_type == "Depreciation Entry":
		adjust_depreciation_entry(doc)
	elif doc.voucher_type == "Asset Disposal":
		from malta_compliance.assets.balancing import on_scrap_entry_submit

		on_scrap_entry_submit(doc)


def adjust_depreciation_entry(doc) -> list[str]:
	"""Posts the adjustment of a depreciation entry of ERPNext; returns the names of the entries created."""
	created = []
	for row in doc.accounts:
		if not (row.reference_type == "Asset" and row.reference_name and flt(row.debit)):
			continue
		if frappe.get_cached_value("Account", row.account, "root_type") != "Expense":
			continue
		asset = frappe.get_doc("Asset", row.reference_name)
		if not allowance.asset_rule(asset):
			continue
		if not frappe.db.exists("Depreciation Schedule", {"journal_entry": doc.name}):
			continue
		warning = rules.review_warning(getdate(doc.posting_date).year)
		if warning:
			frappe.msgprint(warning, indicator="orange", alert=True)
		f, p, r = allowance.deductible_share(asset, doc.posting_date)
		amount = flt(row.debit)
		private = flt((1 - p) * amount, 2)
		non_deductible = flt(p * (1 - r) * amount, 2)
		if not (private or non_deductible):
			continue
		rows = [
			{
				"account": row.account,
				"credit_in_account_currency": flt(private + non_deductible, 2),
				"cost_center": row.cost_center,
			}
		]
		if private:
			rows.append({"account": account(asset.company, DRAWINGS), "debit_in_account_currency": private})
		if non_deductible:
			rows.append(
				{
					"account": account(asset.company, NON_DEDUCTIBLE),
					"debit_in_account_currency": non_deductible,
				}
			)
		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Depreciation Entry",
				"company": doc.company,
				"posting_date": doc.posting_date,
				"finance_book": doc.finance_book,
				"accounts": rows,
				"user_remark": _(
					"Capital allowance adjustment of {0} for asset {1}: business use {2}%, deductible share {3}%"
				).format(doc.name, asset.name, flt(p * 100, 2), flt(f * 100, 2)),
				**adjustment_fields(doc.doctype, doc.name, asset.name),
			}
		)
		je.flags.ignore_permissions = True
		je.insert()
		je.submit()
		created.append(je.name)
	return created


def cancel_adjustments(doctype: str, name: str, asset: str | None = None) -> None:
	filters = {"mc_adjustment_doctype": doctype, "mc_adjustment_for": name, "docstatus": 1}
	if asset:
		filters["mc_asset"] = asset
	for je in frappe.get_all("Journal Entry", filters=filters, pluck="name"):
		adjustment = frappe.get_doc("Journal Entry", je)
		adjustment.flags.ignore_permissions = True
		adjustment.flags.mc_cancel_with_voucher = True
		adjustment.cancel()


def before_journal_entry_cancel(doc, method=None):
	if not doc.get("mc_adjustment_for") or doc.flags.get("mc_cancel_with_voucher"):
		return
	if frappe.db.get_value(doc.mc_adjustment_doctype, doc.mc_adjustment_for, "docstatus") == 1:
		frappe.throw(
			_("This capital allowance adjustment is cancelled together with {0} {1}.").format(
				doc.mc_adjustment_doctype, doc.mc_adjustment_for
			)
		)


def on_journal_entry_cancel(doc, method=None):
	cancel_adjustments(doc.doctype, doc.name)
