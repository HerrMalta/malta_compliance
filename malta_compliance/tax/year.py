"""Figures of a Malta Tax Year record for the reports: the input of the income tax computation from the books and
the entered amounts, the provisional tax benchmark from the record of the basis year two years earlier, and the
Class 2 base from the record of the preceding year. Records of the same taxpayer are found by the field Taxpayer.
"""

from datetime import date
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import getdate

from malta_compliance.tax import books, income_tax, provisional_tax

# Persons of a record.
SELF = "Self"
SPOUSE = "Spouse"

# Kinds of the amounts outside the books, with the boxes of the return.
TRADE = "Trade Profit or Loss"  # box 2
EMPLOYMENT = "Employment or Pension Income"  # boxes 1, 3 and 4
OTHER_INCOME = "Other Income"  # box 15
DEDUCTION = "Deduction"  # box 22
TAX_CREDIT = "Tax Credit"  # boxes 28 to 30
TAX_AT_SOURCE = "Tax at Source"  # boxes 35 and 38 to 40

# Kinds of payments.
PROVISIONAL_TAX = "Provisional Tax"
SETTLEMENT = "Settlement"
CLASS2 = "Class 2 Contribution"

CHILDREN = {"0": 0, "1": 1, "2 or more": 2}


def basis_year(doc) -> int:
	return int(doc.basis_year)


def company_profits(doc) -> list[tuple[str, str, int]]:
	"""(company, person, net profit or loss in whole euro) of each listed company."""
	year = basis_year(doc)
	return [
		(row.company, row.person, income_tax.whole_euro(books.profit(row.company, year)))
		for row in doc.companies
	]


def item_amount(item) -> int:
	"""Amount of an entered row as it enters the return: deductions rounded up, the other kinds without cents."""
	return (
		income_tax.deduction_euro(item.amount)
		if item.kind == DEDUCTION
		else income_tax.whole_euro(item.amount)
	)


def item_total(doc, kind: str, person: str | None = None) -> int:
	return sum(item_amount(i) for i in doc.items if i.kind == kind and (person is None or i.person == person))


def payments(doc, kind: str, person: str | None = None) -> list[tuple[date, Decimal]]:
	return [
		(getdate(p.posting_date), Decimal(str(p.amount)))
		for p in doc.payments
		if p.kind == kind and (person is None or p.person == person)
	]


def payment_total(doc, kind: str, person: str | None = None) -> Decimal:
	return sum((amount for _paid_on, amount in payments(doc, kind, person)), Decimal(0))


def net_earnings(doc, person: str) -> int:
	"""Net profit of the trades of a person in the year, the Class 2 base of the following year."""
	return sum(p for _company, who, p in company_profits(doc) if who == person) + item_total(
		doc, TRADE, person
	)


def earned_income(doc, person: str) -> int:
	return net_earnings(doc, person) + item_total(doc, EMPLOYMENT, person)


def tax_input(doc) -> income_tax.TaxInput:
	return income_tax.TaxInput(
		basis_year=basis_year(doc),
		status=doc.status,
		children=CHILDREN.get(doc.children or "0", 0),
		child_tables=bool(doc.child_tables),
		earned_self=Decimal(earned_income(doc, SELF)),
		earned_spouse=Decimal(earned_income(doc, SPOUSE)),
		other_income=Decimal(item_total(doc, OTHER_INCOME)),
		deductions=Decimal(item_total(doc, DEDUCTION)),
		tax_credits=Decimal(item_total(doc, TAX_CREDIT)),
		tax_at_source=Decimal(item_total(doc, TAX_AT_SOURCE)),
		provisional_tax=payment_total(doc, PROVISIONAL_TAX),
	)


def tax_result(doc) -> income_tax.TaxResult:
	return income_tax.compute(tax_input(doc))


def find(taxpayer: str, year: int):
	"""The record of the taxpayer for the basis year, or None."""
	name = frappe.db.get_value("Malta Tax Year", {"taxpayer": taxpayer, "basis_year": str(year)})
	return frappe.get_doc("Malta Tax Year", name) if name else None


def pt_benchmark(doc) -> tuple[int, str]:
	"""Benchmark of the provisional tax of the year and a note naming its origin: the entered amount, else the tax
	of the record two years earlier, as filed or as computed, less its tax credits and tax at source."""
	if doc.pt_benchmark_entered:
		return income_tax.whole_euro(doc.pt_benchmark), _("Benchmark entered on the record")
	year = provisional_tax.benchmark_year(basis_year(doc))
	earlier = find(doc.taxpayer, year)
	if not earlier:
		return 0, _("No record of basis year {0}: no benchmark, no provisional tax").format(year)
	tax = income_tax.whole_euro(earlier.filed_tax) if earlier.filed else tax_result(earlier).tax_charged
	due = max(0, tax - item_total(earlier, TAX_CREDIT))
	origin = _("as filed") if earlier.filed else _("as computed")
	note = _("Tax charged for basis year {0} {1}, less tax credits and tax at source").format(year, origin)
	return provisional_tax.benchmark(due, item_total(earlier, TAX_AT_SOURCE)), note


def class2_base(doc, person: str) -> tuple[int | None, str]:
	"""Net earnings of the preceding year for the Class 2 rate of a person and a note naming their origin; None
	when neither an entered amount nor a record of the preceding year exists."""
	prefix = "self" if person == SELF else "spouse"
	if doc.get(f"{prefix}_class2_base_entered"):
		return income_tax.whole_euro(doc.get(f"{prefix}_class2_base")), _(
			"Net earnings entered on the record"
		)
	year = basis_year(doc) - 1
	earlier = find(doc.taxpayer, year)
	if not earlier:
		return None, _("No record of {0} and no net earnings entered").format(year)
	return net_earnings(earlier, person), _("Net profit of {0} from the record of that year").format(year)
