"""Income tax computation of a Malta Tax Year record in the order of the Maltese return of income: the net profit
of each company from the books and the entered income, the chargeable income, for a married couple the separate
and the joint computation, the tax charged, tax credits, tax at source, provisional tax and the balance due on the
tax settlement date. The message names the rate tables used with their sources (docs/income-tax.md).
"""

import frappe
from frappe import _
from frappe.utils import flt, formatdate

from malta_compliance.tax import books, income_tax, provisional_tax, rules
from malta_compliance.tax import year as tax_year


def execute(filters=None):
	doc = frappe.get_doc("Malta Tax Year", frappe._dict(filters or {}).malta_tax_year)
	doc.check_permission("read")
	try:
		result = tax_year.tax_result(doc)
	except rules.NotCovered as e:
		frappe.throw(str(e), title=_("Year not covered by the rule register"))
	data = income_rows(doc, result) + tax_rows(result) + payment_rows(doc, result)
	return columns(), data, message(doc, result)


def line(label: str, own=None, spouse=None, total=None, note: str = "") -> dict:
	"""One row of the report."""
	return {"line": label, "own": own, "spouse": spouse, "total": total, "note": note}


def person_line(label: str, person: str, amount, note: str = "") -> dict:
	"""A row with the amount in the column of the person."""
	own = amount if person == tax_year.SELF else None
	return line(label, own, amount if person == tax_year.SPOUSE else None, note=note)


def item_label(item) -> str:
	return f"{_(item.kind)}: {item.description}" if item.description else _(item.kind)


def income_rows(doc, result) -> list[dict]:
	"""Boxes 1 to 23: earned income per person, then other income and deductions."""
	year = tax_year.basis_year(doc)
	rows = []
	for company, person, profit in tax_year.company_profits(doc):
		rows.append(
			person_line(
				_("Net profit or loss: {0}").format(company),
				person,
				profit,
				_("Books, calendar year, each account rounded to the euro"),
			)
		)
		interest = books.interest_income(company, year)
		if interest:
			note = _(
				"{0} on account 4920 is not in the trade profit; enter it as other income unless final tax was withheld"
			)
			rows.append(line(_("Interest income: {0}").format(company), note=note.format(flt(interest, 2))))
	earned = (tax_year.TRADE, tax_year.EMPLOYMENT)
	rows += [
		person_line(item_label(i), i.person, tax_year.item_amount(i), _("Entered"))
		for i in doc.items
		if i.kind in earned
	]
	rows.append(
		line(
			_("Total emolument and business income (box 8)"),
			result.earned_self,
			result.earned_spouse if doc.status == income_tax.MARRIED else None,
		)
	)
	for item in doc.items:
		if item.kind == tax_year.OTHER_INCOME:
			rows.append(line(item_label(item), total=tax_year.item_amount(item), note=_("Entered")))
		elif item.kind == tax_year.DEDUCTION:
			rows.append(line(item_label(item), total=-tax_year.item_amount(item), note=_("Entered")))
	rows.append(line(_("Other income less deductions (box 23)"), total=result.other_net))
	return rows


def table_note(computation) -> str:
	return _("Rates: {0}").format(_(computation.table.category))


def tax_rows(result) -> list[dict]:
	"""Boxes 25 to 27."""
	rows = []
	if result.single:
		rows += computation_rows(result.single, "")
	else:
		own, spouse = result.separate_self, result.separate_spouse
		rows.append(
			line(
				_("Separate computation: chargeable income (box 25)"),
				own.chargeable_income,
				spouse.chargeable_income,
			)
		)
		rows.append(
			line(
				_("Separate computation: tax (box 26)"),
				own.tax,
				spouse.tax,
				own.tax + spouse.tax,
				_("Rates: {0} (separate computation)").format(_(own.table.category)),
			)
		)
		if own.rebate or spouse.rebate:
			rows.append(
				line(
					_("Separate computation: tax rebate (box 26A)"),
					-own.rebate,
					-spouse.rebate,
					-(own.rebate + spouse.rebate),
				)
			)
		rows += computation_rows(result.joint, _("Joint computation: "))
	used = {income_tax.JOINT: _("Joint computation"), income_tax.SEPARATE: _("Separate computation")}
	rows.append(
		line(_("Tax charged (box 27)"), total=result.tax_charged, note=used.get(result.computation, ""))
	)
	return rows


def computation_rows(computation, prefix: str) -> list[dict]:
	rows = [
		line(prefix + _("chargeable income (box 25)"), total=computation.chargeable_income),
		line(prefix + _("tax (box 26)"), total=computation.tax, note=table_note(computation)),
	]
	if computation.rebate:
		rows.append(line(prefix + _("tax rebate (box 26A)"), total=-computation.rebate))
	return rows


def payment_rows(doc, result) -> list[dict]:
	"""Boxes 31 to 42, the payments on settlement and the comparison with the return as filed."""
	at_source = tax_year.item_total(doc, tax_year.TAX_AT_SOURCE)
	provisional = tax_year.payment_total(doc, tax_year.PROVISIONAL_TAX)
	settled = tax_year.settlement_total(doc)
	due = provisional_tax.settlement_date(tax_year.basis_year(doc))
	rows = [
		line(_("Tax credits (box 31)"), total=-result.tax_credits),
		line(_("Tax due after tax credits (box 32)"), total=result.tax_due),
		line(_("Tax at source (boxes 35 and 38 to 40)"), total=-at_source),
		line(_("Provisional tax paid (box 36)"), total=-flt(provisional)),
		line(
			_("Tax underpaid (+) or overpaid (-) (box 42)"),
			total=flt(result.balance),
			note=_("Due on {0}").format(formatdate(due)),
		),
		line(
			_("Paid on settlement"),
			total=-flt(settled),
			note=_("Record of the following year, kind {0}").format(_(tax_year.SETTLEMENT_PRECEDING)),
		),
		line(_("Open"), total=flt(result.balance - settled)),
	]
	if doc.filed:
		rows += [
			line(_("Chargeable income as filed"), total=flt(doc.filed_chargeable_income)),
			line(_("Tax charged as filed (box 27)"), total=flt(doc.filed_tax)),
			line(_("Tax charged: computed less filed"), total=result.tax_charged - flt(doc.filed_tax)),
		]
	return rows


def message(doc, result) -> str:
	lines = []
	warning = rules.review_warning(tax_year.basis_year(doc))
	if warning:
		lines.append(warning)
	for computation in result.computations():
		table = computation.table
		text = _("Rates {0}: {1} ({2}).").format(_(table.category), table.source, table.status)
		if text not in lines:
			lines.append(text)
		if computation.rebate_rule:
			rebate = computation.rebate_rule
			lines.append(_("Tax rebate: {0} ({1}).").format(rebate.source, rebate.status))
	lines.append(
		_(
			"Class 2 contributions of the taxpayer are not deducted (ITA art. 14(1) and 26(a)); they belong on account "
			"3220, not on an expense account."
		)
	)
	interest = rules.monthly_rate(
		rules.TAX_INTEREST, provisional_tax.settlement_date(tax_year.basis_year(doc))
	)
	lines.append(
		_(
			"Tax unpaid after the settlement date bears interest of {0}% a month or part of a month ({1})."
		).format(interest.percent, interest.source)
	)
	missing = tax_year.without_kind(doc)
	if missing:
		lines.append(_("{0} payments of the record have no kind and are not counted.").format(missing))
	return "<br>".join(lines)


def columns() -> list[dict]:
	return [
		{"fieldname": "line", "label": _("Line"), "fieldtype": "Data", "width": 380},
		{"fieldname": "own", "label": _("Self"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "spouse", "label": _("Spouse"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "total", "label": _("Total"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "note", "label": _("Note"), "fieldtype": "Data", "width": 300},
	]
