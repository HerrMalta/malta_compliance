"""Figures of a Malta Tax Year record for the reports: the input of the income tax computation from the books and
the entered amounts, the payments of a year, the provisional tax benchmark from the record of the basis year two
years earlier, and the Class 2 base from the record of the preceding year. Records of the same taxpayer are found
by the field Taxpayer; a year without a record is built from the Malta Taxpayer of that name (tax/taxpayer.py). A
record lists the payments made in its calendar year; a payment for the preceding year carries a kind saying so and
is read by the reports of that year.
"""

from datetime import date
from decimal import Decimal

import frappe
from frappe import _
from frappe.utils import getdate

from malta_compliance.tax import books, income_tax, provisional_tax, rules

# Persons of a record.
SELF = "Self"
SPOUSE = "Spouse"

# Kinds of the amounts outside the books, with the boxes of the return.
TRADE = "Trade Profit or Loss"  # box 2
EMPLOYMENT = "Employment or Pension Income"  # boxes 1, 3 and 4
OTHER_INCOME = "Other Income"  # box 15
DEDUCTION = "Deduction"  # box 22, with the trading losses brought forward of box 21
TAX_CREDIT = "Tax Credit"  # boxes 28 to 30
TAX_AT_SOURCE = "Tax at Source"  # boxes 35 and 38 to 40

# Kinds of payments. A row without a kind, or with the kind Other, is not counted.
PROVISIONAL_TAX = "Provisional Tax"
PROVISIONAL_TAX_PRECEDING = "Provisional Tax of the Preceding Year"
SETTLEMENT_PRECEDING = "Settlement of the Preceding Year"
CLASS2 = "Class 2 Contribution"
CLASS2_PRECEDING = "Class 2 Contribution of the Preceding Year"
OTHER = "Other"

# Kind under which the record of the following year lists a late payment of the kind.
PRECEDING = {PROVISIONAL_TAX: PROVISIONAL_TAX_PRECEDING, CLASS2: CLASS2_PRECEDING}

CHILDREN = {"0": 0, "1": 1, "2 or more": 2}


def basis_year(doc) -> int:
	"""Basis year of the record as a number."""
	return int(doc.basis_year)


def company_profits(doc) -> list[tuple[str, str, int]]:
	"""(company, person, net profit or loss in whole euro) of each listed company."""
	year = basis_year(doc)
	return [
		(row.company, row.person, income_tax.whole_euro(books.profit(row.company, year)))
		for row in doc.companies
	]


def item_amount(item) -> int:
	"""Amount of an entered row as it enters the return: income without cents, a deduction rounded up, tax
	credits and tax at source rounded at fifty cents."""
	if item.kind == DEDUCTION:
		return income_tax.deduction_euro(item.amount)
	if item.kind in (TAX_CREDIT, TAX_AT_SOURCE):
		return income_tax.tax_euro(item.amount)
	return income_tax.whole_euro(item.amount)


def item_total(doc, kind: str, person: str | None = None) -> int:
	"""Total of the entered rows of a kind, of one person or of both."""
	return sum(item_amount(i) for i in doc.items if i.kind == kind and (person is None or i.person == person))


def find(taxpayer: str, year: int):
	"""The record of the taxpayer for the basis year, else the year built from the Malta Taxpayer of that name, or
	None; the user needs the right to read it."""
	name = frappe.db.get_value("Malta Tax Year", {"taxpayer": taxpayer, "basis_year": str(year)})
	if not name:
		from malta_compliance.tax import taxpayer as taxpayer_record

		return taxpayer_record.built_year(taxpayer, year)
	doc = frappe.get_doc("Malta Tax Year", name)
	doc.check_permission("read")
	return doc


def _rows(doc, kind: str, person: str | None) -> list[tuple[date, Decimal]]:
	return [
		(getdate(p.posting_date), Decimal(str(p.amount)))
		for p in doc.payments
		if p.kind == kind and (person is None or p.person == person)
	]


def payments(doc, kind: str, person: str | None = None) -> list[tuple[date, Decimal]]:
	"""(date, amount) of the payments of a kind for the year of the record: its own rows, and the rows of the
	record of the following year listed as payments for the preceding year."""
	rows = _rows(doc, kind, person)
	if kind in PRECEDING:
		later = find(doc.taxpayer, basis_year(doc) + 1)
		if later:
			rows += _rows(later, PRECEDING[kind], person)
	return rows


def payment_total(doc, kind: str, person: str | None = None) -> Decimal:
	"""Total of payments(doc, kind, person)."""
	return sum((amount for _paid_on, amount in payments(doc, kind, person)), Decimal(0))


def settlement_payments(doc) -> list[tuple[date, Decimal]]:
	"""(date, amount) of the tax of the year paid on settlement: the rows of that kind in the record of the
	following year."""
	later = find(doc.taxpayer, basis_year(doc) + 1)
	return _rows(later, SETTLEMENT_PRECEDING, None) if later else []


def settlement_total(doc) -> Decimal:
	"""Total of settlement_payments(doc)."""
	return sum((amount for _paid_on, amount in settlement_payments(doc)), Decimal(0))


def without_kind(doc) -> int:
	"""Number of payment rows without a kind."""
	return sum(1 for p in doc.payments if not p.kind)


def net_earnings(doc, person: str) -> int:
	"""Net profit of the trades of a person in the year, the Class 2 base of the following year."""
	return sum(p for _company, who, p in company_profits(doc) if who == person) + item_total(
		doc, TRADE, person
	)


def earned_income(doc, person: str) -> int:
	"""Income of a person in return boxes 1 to 4."""
	return net_earnings(doc, person) + item_total(doc, EMPLOYMENT, person)


def tax_input(doc) -> income_tax.TaxInput:
	"""Input of the income tax computation from the books and the entered amounts of the record."""
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
	"""Income tax computation of the record."""
	return income_tax.compute(tax_input(doc))


def tax_payable(doc) -> int:
	"""Tax payable of the year before provisional tax: the tax charged, as filed where the return is filed, less
	tax credits and tax at source."""
	if doc.filed:
		charged = income_tax.tax_euro(doc.filed_tax)
	else:
		try:
			charged = tax_result(doc).tax_charged
		except rules.NotCovered:
			frappe.throw(
				_(
					"The record of basis year {0} is not filed and no rate table covers that year: enter its tax "
					"as filed."
				).format(doc.basis_year)
			)
	due = max(0, charged - item_total(doc, TAX_CREDIT))
	return provisional_tax.benchmark(due, item_total(doc, TAX_AT_SOURCE))


def pt_benchmark(doc) -> tuple[int, str]:
	"""Benchmark of the provisional tax of the year and a note naming its origin: the entered amount, else the tax
	payable of the record two years earlier."""
	if doc.pt_benchmark_entered:
		return income_tax.whole_euro(doc.pt_benchmark), _("Benchmark entered on the record")
	year = provisional_tax.benchmark_year(basis_year(doc))
	earlier = find(doc.taxpayer, year)
	if not earlier:
		return 0, _(
			"No record of basis year {0}: benchmark 0. Enter the benchmark of the P.T. demand if one exists"
		).format(year)
	origin = _("as filed") if earlier.filed else _("as computed")
	note = _("Tax charged for basis year {0} {1}, less tax credits and tax at source").format(year, origin)
	return tax_payable(earlier), note


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
