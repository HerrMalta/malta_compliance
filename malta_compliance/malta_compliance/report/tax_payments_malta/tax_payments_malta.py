"""Payments of income tax, provisional tax and Class 2 contributions falling due in a calendar year, for the Malta
Taxpayer listing a company: the balance of the preceding year's tax on the settlement date, the three provisional
tax instalments and the three Class 2 periods of each self-occupied person, by due date, with the amount paid and
the amount open. A saved Malta Tax Year of a year takes precedence over the year built from the Malta Taxpayer
(docs/income-tax.md).
"""

from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from malta_compliance.malta_compliance.report.provisional_tax_malta import provisional_tax_malta
from malta_compliance.malta_compliance.report.social_security_contributions_malta import (
	social_security_contributions_malta as class2_report,
)
from malta_compliance.tax import provisional_tax, rules
from malta_compliance.tax import taxpayer as taxpayer_record
from malta_compliance.tax import year as tax_year


def execute(filters=None):
	filters = frappe._dict(filters or {})
	frappe.has_permission("Malta Taxpayer", "read", throw=True)
	frappe.has_permission("Malta Tax Year", "read", throw=True)
	taxpayer_record.clear_cache()
	year = int(filters.year)
	today = getdate(filters.as_of or nowdate())
	name = taxpayer_record.for_company(filters.company)
	if not name:
		frappe.throw(
			_("No Malta Taxpayer lists the company {0}. Create one under Malta Taxpayer.").format(
				filters.company
			)
		)
	doc = tax_year.find(name, year)
	if doc is None:
		frappe.throw(_("The Malta Taxpayer {0} starts after {1}.").format(name, year))
	lines = [origin(doc)]
	data = []
	previous = tax_year.find(name, year - 1)
	if previous is not None:
		row, text = settlement_row(previous)
		data += [row] if row else []
		lines.append(text)
	try:
		pt_rows, pt_text = provisional_tax_malta.compute(doc, today)
		data += [
			payment_row(
				r["due"], _("Provisional tax, {0}").format(r["instalment"].lower()), "", r, "additional_tax"
			)
			for r in pt_rows
			if r.get("due")
		]
		lines.append(pt_text)
		for person in class2_report.persons(doc):
			rows, text = class2_report.person_rows(doc, person, today)
			data += [
				payment_row(r["due"], _("Class 2, {0}").format(r["period"]), r["person"], r, "addition")
				for r in rows
				if r.get("due")
			]
			lines.append(f"{_(person)}: {text}")
	except rules.NotCovered as e:
		frappe.throw(str(e), title=_("Year not covered by the rule register"))
	# Periods before a self-occupation and instalments of a nil benchmark have nothing due or paid.
	data = [r for r in data if r["amount"] or r["paid"]]
	data.sort(key=lambda r: (r["due"], r["payment"]))
	data.append(
		{
			"payment": _("Total"),
			"person": "",
			**{
				field: flt(sum(r[field] or 0 for r in data), 2)
				for field in ("amount", "paid", "addition", "open")
			},
		}
	)
	return columns(), data, "<br>".join(line for line in lines if line)


def origin(doc) -> str:
	if doc.is_new():
		return _(
			"Built from the Malta Taxpayer {0} and the books; the kinds of the payments on 3210 and 3220 are assigned "
			"by account and amount."
		).format(doc.taxpayer)
	return _(
		"Figures of the saved Malta Tax Year {0}; its entries take precedence over the Malta Taxpayer."
	).format(doc.name)


def payment_row(due, payment: str, person: str, row: dict, addition_field: str) -> dict:
	return {
		"due": due,
		"payment": payment,
		"person": person,
		"amount": flt(row["amount"], 2),
		"paid": flt(row["paid"], 2),
		"paid_on": row.get("paid_on"),
		"addition": flt(row.get(addition_field) or 0, 2),
		"open": flt(row["open"], 2),
	}


def settlement_row(previous) -> tuple[dict | None, str]:
	"""Balance of the tax of the preceding year due on its settlement date, and a note on its origin."""
	basis = tax_year.basis_year(previous)
	try:
		payable = Decimal(tax_year.tax_payable(previous))
	except (rules.NotCovered, frappe.ValidationError) as e:
		return None, _("Income tax {0}: {1}").format(basis, e)
	provisional = tax_year.payment_total(previous, tax_year.PROVISIONAL_TAX)
	balance = payable - provisional
	payments = tax_year.settlement_payments(previous)
	paid = sum((amount for _paid_on, amount in payments), Decimal(0))
	row = {
		"due": provisional_tax.settlement_date(basis),
		"payment": _("Income tax {0}, balance").format(basis)
		if balance >= 0
		else _("Income tax {0}, refund").format(basis),
		"person": "",
		"amount": flt(balance, 2),
		"paid": flt(paid, 2),
		"paid_on": max(d for d, _amount in payments) if payments else None,
		"addition": 0,
		"open": flt(balance - paid, 2),
	}
	how = _("as filed") if previous.filed else _("computed from the books and the entered amounts")
	interest = rules.monthly_rate(rules.TAX_INTEREST, row["due"])
	text = _(
		"Income tax {0}: tax payable {1} ({2}) less provisional tax paid {3}; tax unpaid after the settlement date "
		"bears interest of {4}% a month or part of a month ({5})."
	).format(basis, int(payable), how, f"{provisional:.2f}", interest.percent, interest.source)
	return row, text


def columns() -> list[dict]:
	return [
		{"fieldname": "due", "label": _("Due"), "fieldtype": "Date", "width": 110},
		{"fieldname": "payment", "label": _("Payment"), "fieldtype": "Data", "width": 260},
		{"fieldname": "person", "label": _("Person"), "fieldtype": "Data", "width": 80},
		{"fieldname": "amount", "label": _("Amount Due"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "paid", "label": _("Paid"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "paid_on", "label": _("Last Payment"), "fieldtype": "Date", "width": 110},
		{"fieldname": "addition", "label": _("Late Addition"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "open", "label": _("Open"), "fieldtype": "Currency", "width": 130},
	]
