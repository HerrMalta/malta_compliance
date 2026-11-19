"""Provisional tax of the basis year of a Malta Tax Year record under S.L. 372.18: the benchmark, the three
instalments with their due dates, the payments applied in the order of the instalments, and the additional tax on
parts paid late or unpaid on the as-of date (docs/income-tax.md).
"""

from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, nowdate

from malta_compliance.tax import allocation, income_tax, provisional_tax, rules
from malta_compliance.tax import year as tax_year


def execute(filters=None):
	filters = frappe._dict(filters or {})
	doc = frappe.get_doc("Malta Tax Year", filters.malta_tax_year)
	doc.check_permission("read")
	data, text = compute(doc, getdate(filters.as_of or nowdate()))
	return columns(), data, text


def compute(doc, today) -> tuple[list[dict], str]:
	"""Rows of the three instalments with a total row, and the message, of a saved or built record."""
	year = tax_year.basis_year(doc)
	benchmark, origin = tax_year.pt_benchmark(doc)
	payments = tax_year.payments(doc, tax_year.PROVISIONAL_TAX)
	reduced = income_tax.whole_euro(doc.pt_reduced_total) if doc.pt_reduced else None
	instalments = provisional_tax.instalments(
		benchmark,
		year,
		reduced,
		getdate(doc.pt_reduced_on) if doc.pt_reduced else None,
		lambda until: sum((amount for paid_on, amount in payments if paid_on <= until), Decimal(0)),
	)
	parts, excess = allocation.allocate([i.amount for i in instalments], payments)
	data, late_rows = [], []
	for instalment, paid_parts in zip(instalments, parts, strict=True):
		paid = allocation.paid(paid_parts)
		late = allocation.late_parts(
			instalment.amount,
			instalment.due,
			paid_parts,
			today,
			lambda amount, due, until: provisional_tax.additional_tax(amount, due, until, year),
		)
		late_rows.append((instalment.amount, late))
		data.append(
			{
				"instalment": _("Instalment {0}").format(instalment.number),
				"due": instalment.due,
				"share": instalment.share,
				"amount": instalment.amount,
				"paid": flt(paid),
				"paid_on": max(d for d, _amount in paid_parts) if paid_parts else None,
				"additional_tax": flt(allocation.late_addition(late)),
				"open": flt(Decimal(instalment.amount) - paid),
			}
		)
	data.append(
		{
			"instalment": _("Total"),
			"amount": flt(sum(row["amount"] for row in data), 2),
			"paid": flt(sum(row["paid"] for row in data), 2),
			"additional_tax": flt(sum(row["additional_tax"] for row in data), 2),
			"open": flt(sum(row["open"] for row in data), 2),
		}
	)
	return data, message(doc, benchmark, origin, reduced, excess, late_rows)


def message(doc, benchmark: int, origin: str, reduced, excess: Decimal, late_rows: list) -> str:
	lines = []
	warning = rules.review_warning(tax_year.basis_year(doc))
	if warning:
		lines.append(warning)
	lines.append(_("Benchmark {0}: {1} ({2}).").format(benchmark, origin, rules.PT_SOURCE))
	if reduced is not None:
		lines.append(
			_(
				"P.T. Reduction Form: the instalments due from {0} are limited to an estimated tax of {1} less the "
				"provisional tax already paid (rule 10). Additional tax is due on the shortfall if the tax of the "
				"year is higher."
			).format(formatdate(doc.pt_reduced_on), reduced)
		)
	if excess:
		lines.append(
			_("Payments of {0} exceed the instalments; they are set off against the tax of the year.").format(
				flt(excess)
			)
		)
	if any(added for _amount, parts in late_rows for _part, added in parts):
		lines.append(
			_(
				"Additional tax: for each month after the month of the due date, up to the tax settlement date, at "
				"the rate in force in that month, 0.6% from June 2022 (S.L. 372.18 rule 14)."
			)
		)
		final = tax_year.tax_payable(doc)
		remitted = provisional_tax.reduction(late_rows, final)
		if remitted:
			basis = _("as filed") if doc.filed else _("as computed from the record")
			lines.append(
				_(
					"The tax of the year {0} ({1}) is below the benchmark: {2} of the additional tax is remitted, 90% "
					"of the amount on the provisional tax above the tax of the year (rule 14(1), last proviso)."
				).format(basis, final, flt(remitted))
			)
	missing = tax_year.without_kind(doc)
	if missing:
		lines.append(_("{0} payments of the record have no kind and are not counted.").format(missing))
	return "<br>".join(lines)


def columns() -> list[dict]:
	return [
		{"fieldname": "instalment", "label": _("Instalment"), "fieldtype": "Data", "width": 140},
		{"fieldname": "due", "label": _("Due"), "fieldtype": "Date", "width": 110},
		{"fieldname": "share", "label": _("Share (%)"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "amount", "label": _("Amount Due"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "paid", "label": _("Paid"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "paid_on", "label": _("Last Payment"), "fieldtype": "Date", "width": 110},
		{"fieldname": "additional_tax", "label": _("Additional Tax"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "open", "label": _("Open"), "fieldtype": "Currency", "width": 130},
	]
