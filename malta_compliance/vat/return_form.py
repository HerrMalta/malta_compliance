"""Maltese VAT return of a registration under Article 10, computed from the invoices of a period, in the lines of
the tax accountant's worksheet with the boxes of the return form, and the amounts of the settlement entry that
clears the VAT accounts of a period. Imports no Frappe; amounts are cents, positive VAT payable is owed to the
Commissioner for Revenue and negative VAT payable is an excess credit.

The VAT of purchases, self-charged and deducted, is the rate times the tax base of each line, kept exact and
rounded only when shown, so that totals and box 17 come from the unrounded values; the VAT of sales is the VAT
as invoiced. Both reproduce the tax accountant's returns, which differ by cents from the VAT booked per invoice.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from malta_compliance.vat.categories import BASE, DIRECTION, INPUT, OUTPUT, PURCHASE, RATE, TARGETS

# Kinds of line.
SECTION = "section"
BOX = "box"
SUB = "sub"
TOTAL = "total"
FINAL = "final"
RESULT = "result"

# Columns a line fills.
BOTH = "both"
BASE_ONLY = "base"
TAX_ONLY = "tax"


@dataclass(frozen=True)
class Line:
	"""A line of the return. base_box and tax_box are the form's box numbers of its two columns; rate is the VAT
	rate of the invoices a sub-line receives from a category with a RATE target."""

	key: str
	label: str
	kind: str
	base_box: str = ""
	tax_box: str = ""
	parent: str = ""
	rate: float | None = None
	columns: str = BOTH

	@property
	def box(self) -> str:
		return "/".join(b for b in (self.base_box, self.tax_box) if b)


def _box(key: str, label: str, base_box: str, tax_box: str = "") -> Line:
	return Line(key, label, BOX, base_box, tax_box, columns=BOTH if tax_box else BASE_ONLY)


def _sub(key: str, parent: str, label: str, rate: float | None = None, columns: str = BOTH) -> Line:
	return Line(key, label, SUB, parent=parent, rate=rate, columns=columns)


LINES = (
	Line("ic", "Intra-community and Non-EU Trade", SECTION),
	_box(
		"1", "Exempt IC Supplies of Goods and Supplies of Services where customer is liable for the tax", "1"
	),
	_box("2", "Supplies of Goods and Services where place of supply is outside Malta - EU and non EU", "2"),
	_box("3", "IC Acquisition of Goods and Services received from other EU member states", "3", "6"),
	_sub("3_ic", "3", "IC Acquisitions"),
	_sub("3_nr5", "3", "IC Acquisitions Non Recoverable VAT 5%", rate=5),
	_sub("3_nr18", "3", "IC Acquisitions Non Recoverable VAT 18%", rate=18),
	_box(
		"4",
		'Goods and Services received where place of supply is Malta other than those reported in "Box 3"',
		"4",
		"7",
	),
	_sub("4_malta", "4", "Goods and Services received where place of supply is Malta"),
	_sub("4_nr", "4", "Non-EU Services Place of Supply is Malta Non-Recoverable VAT"),
	Line("5", "Subtotal", TOTAL, "5", "8"),
	Line("rc", "Reverse charge", SECTION),
	_box("9", "IC Acquisition of goods for re-sale", "9", "13"),
	_sub("9_rc0", "9", "IC Acquisition of Goods for re-sale RC 0%", rate=0, columns=BASE_ONLY),
	_sub("9_rc5", "9", "IC Acquisition of Goods for re-sale RC5%", rate=5),
	_sub("9_rc18", "9", "IC Acquisition of Goods for re-sale RC18%", rate=18),
	_box("9a", "Services received from EU member states where the purchaser is liable for VAT", "9a", "13a"),
	_box("10", "IC Acquisition of Capital Goods", "10", "14"),
	_sub("10_rc18", "10", "IC Acquisitions Capital Goods RC18%", rate=18),
	_sub("10_rc5", "10", "IC Acquisitions Capital Goods RC5%", rate=5),
	_box("11", "Goods and Services received where place of supply is Malta", "11", "15"),
	Line("12", "Subtotal", TOTAL, "12", "16"),
	Line("17", "Total intra-community and non-EU trade (Box 8 - Box 16)", TOTAL, tax_box="17"),
	Line("dom", "Domestic supplies and exports", SECTION),
	_box("18", "Taxable Goods/Services at 18%", "18", "23"),
	_sub("18_taxable", "18", "Taxable Goods/Services 18%"),
	_sub("18_danger", "18", "Goods/Services Tax in Danger", columns=BASE_ONLY),
	_box("18a", "Taxable Services at 7%", "18a", "23a"),
	_box("18b", "Taxable Services at 12%", "18b", "23b"),
	_box("19", "Taxable Goods/Services at 5%", "19", "24"),
	_box("20", "Exempt with Credit/Exports", "20"),
	_box("21", "Exempt without Credit", "21"),
	Line("22", "Subtotal", TOTAL, "22", "25"),
	Line("26", "Total (Box 17 + Box 25)", TOTAL, tax_box="26", columns=TAX_ONLY),
	Line("pur", "Domestic purchases and imports", SECTION),
	_box("27", "Taxable Purchases for re-sale at 18%", "27", "34"),
	_box("28", "Taxable Purchases for re-sale at 5%", "28", "35"),
	_box("29", "Exempt Purchases for re-sale", "29"),
	_box("30", "Capital Goods", "30", "36"),
	_sub("30_18", "30", "Capital Goods 18%", rate=18),
	_sub("30_5", "30", "Capital Goods 5%", rate=5),
	_box("31", "Services and overheads at 18%", "31", "37"),
	_box("31a", "Services and overheads at 7%", "31a", "37a"),
	_box("31b", "Services and overheads at 12%", "31b", "37b"),
	_box("32", "Services and overheads at 5%", "32", "38"),
	Line("33", "Subtotal", TOTAL, "33", "39"),
	Line("40", "Adjustment in favour of VAT department", FINAL, tax_box="40", columns=TAX_ONLY),
	Line("41", "Adjustment in favour of registered person", FINAL, tax_box="41", columns=TAX_ONLY),
	Line(
		"42",
		"VAT payable or excess credit (Box 26 + Box 40 - Box 39 - Box 41)",
		FINAL,
		tax_box="42",
		columns=TAX_ONLY,
	),
	Line("excess", "Excess Credit", RESULT, columns=TAX_ONLY),
	Line("bf", "Excess Credit B/F", RESULT, columns=TAX_ONLY),
	Line("payable", "Tax Payable", RESULT, columns=TAX_ONLY),
)
LINE = {line.key: line for line in LINES}
SUB_BY_RATE = {
	(line.parent, line.rate): line.key for line in LINES if line.kind == SUB and line.rate is not None
}

# Subtotals of the form: the lines summed in both columns.
SUBTOTALS = {
	"5": ("1", "2", "3", "4"),
	"12": ("9", "9a", "10", "11"),
	"22": ("18", "18a", "18b", "19", "20", "21"),
	"33": ("27", "28", "29", "30", "31", "31a", "31b", "32"),
}

QUARTERS = {"Jan-Mar": 1, "Apr-Jun": 4, "Jul-Sep": 7, "Oct-Dec": 10}
OTHER_DATES = "Other dates"

# Largest difference in cents between the VAT payable as filed and the books that a settlement books to Round Off.
MAX_ROUNDING = 10


@dataclass(frozen=True)
class Invoice:
	"""A submitted invoice of the period. base is the net total in company currency; output_vat is the VAT charged on
	a sale or self-charged on a purchase, input_vat the VAT deducted; rates are the rates of its VAT rows."""

	doctype: str
	name: str
	posting_date: date | str
	party: str
	category: str
	base: int
	output_vat: int = 0
	input_vat: int = 0
	rates: tuple[float, ...] = ()


@dataclass
class Result:
	"""amounts: [tax base, exact tax amount] per line key. entries: the invoices of each line with their tax base
	and booked VAT, on the sub-line where one receives them. outside: invoices of the category without a return
	box; unknown: invoices without a category of the return. booked: the VAT payable of the counted invoices as
	booked, which the VAT accounts hold."""

	amounts: dict[str, list]
	entries: dict[str, list[tuple[Invoice, int, int]]] = field(default_factory=dict)
	counted: list[Invoice] = field(default_factory=list)
	outside: list[Invoice] = field(default_factory=list)
	unknown: list[Invoice] = field(default_factory=list)
	notes: list[str] = field(default_factory=list)
	booked: int = 0

	def base(self, key: str) -> int:
		return self.amounts[key][0]

	def tax(self, key: str) -> int:
		"""The tax amount of a line in whole cents, as shown."""
		return shown(self.amounts[key][1])


def shown(value) -> int:
	"""Exact cents rounded to whole cents, half away from zero."""
	value = Fraction(value)
	exact = Decimal(value.numerator) / Decimal(value.denominator)
	return int(exact.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def money(cents: int) -> str:
	return f"{cents / 100:,.2f}"


def single_rate(invoice: Invoice) -> float | None:
	"""The rate of the invoice's VAT rows: 0 without rows, None for rows of different rates."""
	rates = {round(float(r), 2) for r in invoice.rates}
	if not rates:
		return 0
	if len(rates) > 1:
		return None
	rate = rates.pop()
	return int(rate) if rate.is_integer() else rate


def compute(
	invoices: list[Invoice],
	adjustment_vat_department: int = 0,
	adjustment_registered_person: int = 0,
	credit_bf: int = 0,
) -> Result:
	result = Result(amounts={line.key: [0, 0] for line in LINES})
	amounts = result.amounts

	def enter(key: str, invoice: Invoice, tax, booked: int, listed: bool) -> None:
		amounts[key][0] += invoice.base
		amounts[key][1] += tax
		if listed:
			result.entries.setdefault(key, []).append((invoice, invoice.base, booked))

	for invoice in invoices:
		targets = TARGETS.get(invoice.category or "")
		if targets is None:
			result.unknown.append(invoice)
			continue
		if not targets:
			result.outside.append(invoice)
			continue
		result.counted.append(invoice)
		parts = {part for _line, _sub, part in targets}
		for vat, part, name in ((invoice.output_vat, OUTPUT, "output"), (invoice.input_vat, INPUT, "input")):
			if vat and part not in parts:
				result.notes.append(
					f"{invoice.name}: {name} VAT {money(vat)} in the category {invoice.category}, whose boxes hold "
					f"no {name} VAT; not counted."
				)
		result.booked += (invoice.output_vat if OUTPUT in parts else 0) - (
			invoice.input_vat if INPUT in parts else 0
		)
		rate = single_rate(invoice)
		computed = DIRECTION[invoice.category] == PURCHASE and rate is not None
		if DIRECTION[invoice.category] == PURCHASE and rate is None:
			result.notes.append(f"{invoice.name}: VAT rows of different rates; its VAT is counted as booked.")
		for line_key, selector, part in targets:
			booked = {OUTPUT: invoice.output_vat, INPUT: invoice.input_vat}.get(part, 0)
			tax = invoice.base * Fraction(str(rate)) / 100 if computed and part != BASE else booked
			sub_key = selector
			if selector == RATE:
				sub_key = SUB_BY_RATE.get((line_key, rate))
				if sub_key is None:
					what = "VAT rows of different rates" if rate is None else f"the rate {rate}%"
					result.notes.append(
						f"{invoice.name}: {what}, no sub-line of box {LINE[line_key].box}; counted in the box only."
					)
			enter(line_key, invoice, tax, booked, listed=not sub_key)
			if sub_key:
				enter(sub_key, invoice, tax, booked, listed=True)

	for key, members in SUBTOTALS.items():
		amounts[key] = [sum(amounts[m][0] for m in members), sum(amounts[m][1] for m in members)]
	amounts["17"] = [amounts["5"][0] - amounts["12"][0], amounts["5"][1] - amounts["12"][1]]
	amounts["26"] = [0, amounts["17"][1] + amounts["22"][1]]
	amounts["40"] = [0, adjustment_vat_department]
	amounts["41"] = [0, adjustment_registered_person]
	box42 = amounts["26"][1] + adjustment_vat_department - amounts["33"][1] - adjustment_registered_person
	amounts["42"] = [0, box42]
	payable = box42 - credit_bf
	amounts["excess"] = [0, -payable if payable < 0 else 0]
	amounts["bf"] = [0, credit_bf]
	amounts["payable"] = [0, payable]
	return result


def period_dates(year: int, period: str, from_date: date | None = None, to_date: date | None = None):
	"""First and last day of a return period: a calendar quarter of the year, or the given dates for OTHER_DATES."""
	if period in QUARTERS:
		first = QUARTERS[period]
		last = first + 2
		return date(year, first, 1), date(year, last, calendar.monthrange(year, last)[1])
	if period == OTHER_DATES:
		if not from_date or not to_date:
			raise ValueError("The period Other dates needs a From Date and a To Date.")
		if from_date > to_date:
			raise ValueError("The From Date is after the To Date.")
		return from_date, to_date
	raise ValueError(f"Unknown period {period}.")


def period_label(from_date: date, to_date: date) -> str:
	"""The quarter as "Jul - Sep 2026", any other period by its dates."""
	for name in QUARTERS:
		if (from_date, to_date) == period_dates(from_date.year, name):
			return f"{name.replace('-', ' - ')} {from_date.year}"
	return f"{from_date.day} {from_date:%b %Y} - {to_date.day} {to_date:%b %Y}"


@dataclass(frozen=True)
class Settlement:
	"""Amounts (debit minus credit) of a settlement entry: per VAT account key, on the settlement account and on
	Round Off. computed is the VAT payable of the books."""

	accounts: dict[str, int]
	settlement: int
	rounding: int
	computed: int


def settlement(movements: dict[str, int], filed: int) -> Settlement:
	"""Clears the movements (debit minus credit) of the VAT accounts in a period against the settlement account at
	the VAT payable as filed, with the difference to the books on Round Off. Raises ValueError for a difference
	above MAX_ROUNDING."""
	computed = -sum(movements.values())
	difference = filed - computed
	if abs(difference) > MAX_ROUNDING:
		raise ValueError(
			f"The VAT payable as filed, {money(filed)}, differs from the books, {money(computed)}, by "
			f"{money(difference)}. A difference above {money(MAX_ROUNDING)} is not booked as rounding: correct "
			"the books, or book a settlement with adjustments of boxes 40 and 41 as a Journal Entry by hand."
		)
	return Settlement(
		accounts={key: -amount for key, amount in movements.items() if amount},
		settlement=-filed,
		rounding=difference,
		computed=computed,
	)
