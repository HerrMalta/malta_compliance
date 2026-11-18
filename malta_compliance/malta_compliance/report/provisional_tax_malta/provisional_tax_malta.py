"""Provisional tax of the basis year of a Malta Tax Year record under S.L. 372.18: the benchmark, the three
instalments with their due dates, the payments of the record applied in the order of the instalments, and the
additional tax on parts paid late or unpaid on the as-of date (docs/income-tax.md).
"""

from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from malta_compliance.tax import allocation, income_tax, provisional_tax, rules
from malta_compliance.tax import year as tax_year


def execute(filters=None):
	filters = frappe._dict(filters or {})
	doc = frappe.get_doc("Malta Tax Year", filters.malta_tax_year)
	doc.check_permission("read")
	today = getdate(filters.as_of or nowdate())
	year = tax_year.basis_year(doc)
	benchmark, origin = tax_year.pt_benchmark(doc)
	reduced = income_tax.whole_euro(doc.pt_reduced_total) if doc.pt_reduced else None
	instalments = provisional_tax.instalments(benchmark, year, reduced)
	parts, excess = allocation.allocate(
		[i.amount for i in instalments], tax_year.payments(doc, tax_year.PROVISIONAL_TAX)
	)
	data, reduction_rows = [], []
	for instalment, paid_parts in zip(instalments, parts, strict=True):
		paid = allocation.paid(paid_parts)
		added = allocation.late_addition(
			instalment.amount,
			instalment.due,
			paid_parts,
			today,
			lambda amount, due, until: provisional_tax.additional_tax(amount, due, until, year),
		)
		reduction_rows.append((instalment.amount, Decimal(instalment.amount) - paid, added))
		data.append(
			{
				"instalment": _("Instalment {0}").format(instalment.number),
				"due": instalment.due,
				"share": instalment.share,
				"amount": instalment.amount,
				"paid": flt(paid),
				"paid_on": max(d for d, _amount in paid_parts) if paid_parts else None,
				"additional_tax": flt(added),
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
	return columns(), data, message(doc, benchmark, origin, reduced, excess, reduction_rows, today)


def message(doc, benchmark: int, origin: str, reduced, excess: Decimal, reduction_rows: list, today) -> str:
	year = tax_year.basis_year(doc)
	lines = []
	warning = rules.review_warning(year)
	if warning:
		lines.append(warning)
	lines.append(_("Benchmark {0}: {1} ({2}).").format(benchmark, origin, rules.PT_SOURCE))
	if reduced is not None:
		lines.append(
			_(
				"P.T. Reduction Form: the instalments are limited to an estimated tax of {0} (rule 10). Additional tax "
				"is due on the shortfall if the tax of the year is higher."
			).format(reduced)
		)
	if excess:
		lines.append(
			_("Payments of {0} exceed the instalments; they are set off against the tax of the year.").format(
				flt(excess)
			)
		)
	if any(added for _amount, _unpaid, added in reduction_rows):
		result = tax_year.tax_result(doc)
		final = max(0, result.tax_due - tax_year.item_total(doc, tax_year.TAX_AT_SOURCE))
		remitted = provisional_tax.reduction(reduction_rows, final)
		if remitted:
			lines.append(
				_(
					"The tax of the year computed from the record ({0}) is below the benchmark: {1} of the additional "
					"tax on unpaid instalments is remitted (rule 14(1), last proviso)."
				).format(final, flt(remitted))
			)
		rate = rules.monthly_rate(rules.PT_ADDITIONAL_TAX, today)
		lines.append(
			_(
				"Additional tax: {0}% for each month after the month of the due date, up to the tax settlement date "
				"({1})."
			).format(rate.percent, rate.source)
		)
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
