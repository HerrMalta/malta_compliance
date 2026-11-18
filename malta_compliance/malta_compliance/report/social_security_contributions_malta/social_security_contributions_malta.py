"""Class 2 contributions of the contribution year of a Malta Tax Year record: per self-occupied person the weekly
rate from the net earnings of the preceding year, the three periods with their weeks and due dates, the payments of
the record applied in the order of the periods, and the addition on parts paid late or unpaid on the as-of date
(docs/income-tax.md).
"""

from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from malta_compliance.tax import allocation, class2, income_tax, rules
from malta_compliance.tax import year as tax_year

PERIOD_LABELS = ("January to April", "May to August", "September to December")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	doc = frappe.get_doc("Malta Tax Year", filters.malta_tax_year)
	doc.check_permission("read")
	today = getdate(filters.as_of or nowdate())
	data, lines = [], []
	warning = rules.review_warning(tax_year.basis_year(doc))
	if warning:
		lines.append(warning)
	for person in persons(doc):
		rows, text = person_rows(doc, person, today)
		data += rows
		lines.append(f"{_(person)}: {text}")
	return columns(), data, "<br>".join(lines)


def persons(doc) -> list[str]:
	"""The persons with a trade in the record: a listed company, an entered trade profit, entered net earnings or a
	Class 2 payment."""
	found = []
	for person, prefix in ((tax_year.SELF, "self"), (tax_year.SPOUSE, "spouse")):
		if person == tax_year.SPOUSE and doc.status != income_tax.MARRIED:
			continue
		if (
			any(row.person == person for row in doc.companies)
			or any(i.person == person and i.kind == tax_year.TRADE for i in doc.items)
			or doc.get(f"{prefix}_class2_base_entered")
			or doc.get(f"{prefix}_first_year")
			or tax_year.payments(doc, tax_year.CLASS2, person)
		):
			found.append(person)
	return found


def person_rows(doc, person: str, today) -> tuple[list[dict], str]:
	prefix = "self" if person == tax_year.SELF else "spouse"
	year = tax_year.basis_year(doc)
	first_year = bool(doc.get(f"{prefix}_first_year"))
	base, origin = tax_year.class2_base(doc, person)
	if base is None and not first_year:
		return [], origin
	weekly = class2.weekly_rate(year, base or 0, bool(doc.get(f"{prefix}_born_before_1962")), first_year)
	periods = class2.periods(
		year,
		weekly.rate,
		getdate(doc.get(f"{prefix}_active_from")) if doc.get(f"{prefix}_active_from") else None,
		getdate(doc.get(f"{prefix}_active_to")) if doc.get(f"{prefix}_active_to") else None,
	)
	parts, excess = allocation.allocate(
		[p.amount for p in periods], tax_year.payments(doc, tax_year.CLASS2, person)
	)
	rows = []
	for period, paid_parts in zip(periods, parts, strict=True):
		paid = allocation.paid(paid_parts)
		rows.append(
			{
				"person": _(person),
				"period": _(PERIOD_LABELS[period.number - 1]),
				"weeks": period.weeks,
				"category": weekly.category,
				"weekly_rate": flt(weekly.rate),
				"due": period.due,
				"amount": flt(period.amount),
				"paid": flt(paid),
				"paid_on": max(d for d, _amount in paid_parts) if paid_parts else None,
				"addition": flt(
					allocation.late_addition(
						period.amount, period.due, paid_parts, today, class2.late_addition
					)
				),
				"open": flt(period.amount - paid),
			}
		)
	rows.append(
		{
			"person": _(person),
			"period": _("Total"),
			"weeks": sum(row["weeks"] for row in rows),
			"amount": flt(sum(row["amount"] for row in rows), 2),
			"paid": flt(sum(row["paid"] for row in rows), 2),
			"addition": flt(sum(row["addition"] for row in rows), 2),
			"open": flt(sum(row["open"] for row in rows), 2),
		}
	)
	return rows, note(weekly, base, origin, first_year, excess)


def note(weekly, base, origin: str, first_year: bool, excess: Decimal) -> str:
	table = weekly.table
	if first_year:
		text = _("first calendar year of the self-occupation, lowest rate {0}").format(class2.SA)
	else:
		text = _("{0}: {1}, category {2}").format(origin, base, weekly.category)
		if base <= rules.CLASS2_THRESHOLD:
			text += _("; a person is self-occupied only with earnings above {0} a year (SSA art. 2)").format(
				rules.CLASS2_THRESHOLD
			)
	text += _("; rates of {0}: {1} ({2})").format(table.year, table.source, table.status)
	if excess:
		text += _("; payments of {0} exceed the contributions of the year").format(flt(excess))
	return text + "."


def columns() -> list[dict]:
	return [
		{"fieldname": "person", "label": _("Person"), "fieldtype": "Data", "width": 90},
		{"fieldname": "period", "label": _("Period"), "fieldtype": "Data", "width": 170},
		{"fieldname": "weeks", "label": _("Weeks"), "fieldtype": "Int", "width": 70},
		{"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 90},
		{"fieldname": "weekly_rate", "label": _("Weekly Rate"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "due", "label": _("Due"), "fieldtype": "Date", "width": 110},
		{"fieldname": "amount", "label": _("Amount Due"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "paid", "label": _("Paid"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "paid_on", "label": _("Last Payment"), "fieldtype": "Date", "width": 110},
		{"fieldname": "addition", "label": _("Late Addition"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "open", "label": _("Open"), "fieldtype": "Currency", "width": 130},
	]
