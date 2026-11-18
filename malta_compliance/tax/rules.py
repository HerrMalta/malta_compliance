"""Register of the Maltese income tax, provisional tax and Class 2 contribution rules applied by the app, each with
the period in which it applies, its source and the status of that source (docs/income-tax.md). Rate tables are
selected by basis year, Class 2 tables by contribution year, monthly rates by a date. Year of assessment N belongs
to basis year N - 1. A year or date outside every version raises NotCovered. REVIEWED_UP_TO is the last basis and
contribution year checked against the sources; later years produce a warning. No Frappe imports.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

# Last basis year and contribution year checked against the sources.
REVIEWED_UP_TO = 2027

# Status of a source.
LAW = "law"
MTCA_TABLE = "MTCA table, Legal Notice outstanding"
MTCA_GUIDE = "MTCA return guide, in no version of the Act"
ANNOUNCED = "Budget speech, implementing Act outstanding"

# Categories of the rate tables of ITA art. 56(1).
SINGLE = "Single"
MARRIED = "Married"
PARENT = "Parent"
MARRIED_ONE_CHILD = "Married, one child"
MARRIED_TWO_CHILDREN = "Married, two or more children"
PARENT_ONE_CHILD = "Parent, one child"
PARENT_TWO_CHILDREN = "Parent, two or more children"


class NotCovered(Exception):
	"""The year or date lies outside every version of a rule."""


@dataclass(frozen=True)
class Band:
	"""Chargeable income up to and including `upper` (None: no limit): tax = income x rate % - subtract."""

	upper: int | None
	rate: int
	subtract: int


@dataclass(frozen=True)
class RateTable:
	"""Rates of one category for the basis years first to last; last None means open-ended."""

	category: str
	first: int
	last: int | None
	bands: tuple[Band, ...]
	source: str
	status: str


@dataclass(frozen=True)
class BracketRebate:
	"""Rebate of return section 26A: for chargeable income above `above` and below `below` the tax is reduced until
	income less tax equals `net`."""

	category: str
	first: int
	last: int
	above: int
	below: int
	net: int
	source: str
	status: str


@dataclass(frozen=True)
class MonthlyRate:
	"""Percentage per calendar month or part of a month, for the dates first to last; last None means open-ended."""

	first: date
	last: date | None
	percent: Decimal
	source: str


@dataclass(frozen=True)
class Class2Table:
	"""Weekly Class 2 rates of a self-occupied person for one contribution year (SSA Tenth Schedule Part III). SA
	applies to net earnings up to sa_upper, 15% to earnings up to sb_upper, SC above; the SB limit and the SC rate
	depend on the year of birth."""

	year: int
	sa_rate: Decimal
	sa_upper: Decimal
	sb_upper_before_1962: Decimal
	sc_rate_before_1962: Decimal
	sb_upper_from_1962: Decimal
	sc_rate_from_1962: Decimal
	source: str
	status: str


def _table(category: str, first: int, last: int | None, source: str, status: str, *rows: tuple) -> RateTable:
	return RateTable(category, first, last, tuple(Band(*row) for row in rows), source, status)


_ACT_2016 = "ITA art. 56(1) as substituted by Act XV of 2016 art. 20"
_ACT_2025 = "ITA art. 56(1) as substituted by Act IX of 2025 art. 15"
_ACT_2026 = "ITA art. 56(1) as substituted by Act III of 2026 art. 19"
_BUDGET_2027 = "Budget Speech 2027 of 26 October 2026, tables for 2027 and 2028"

# Basis years before 2020 are not covered. The tables of Act III of 2026 for taxpayers with children stay in force
# after basis year 2026 until an Act replaces them; the register applies the announced tables from 2027.
RATE_TABLES = (
	_table(
		SINGLE,
		2020,
		2024,
		_ACT_2016,
		LAW,
		(9100, 0, 0),
		(14500, 15, 1365),
		(19500, 25, 2815),
		(60000, 25, 2725),
		(None, 35, 8725),
	),
	_table(
		MARRIED,
		2020,
		2024,
		_ACT_2016,
		LAW,
		(12700, 0, 0),
		(21200, 15, 1905),
		(28700, 25, 4025),
		(60000, 25, 3905),
		(None, 35, 9905),
	),
	_table(
		PARENT,
		2020,
		2024,
		_ACT_2016,
		LAW,
		(10500, 0, 0),
		(15800, 15, 1575),
		(21200, 25, 3155),
		(60000, 25, 3050),
		(None, 35, 9050),
	),
	_table(
		SINGLE,
		2025,
		None,
		_ACT_2025,
		LAW,
		(12000, 0, 0),
		(16000, 15, 1800),
		(60000, 25, 3400),
		(None, 35, 9400),
	),
	_table(
		MARRIED,
		2025,
		None,
		_ACT_2025,
		LAW,
		(15000, 0, 0),
		(23000, 15, 2250),
		(60000, 25, 4550),
		(None, 35, 10550),
	),
	_table(
		PARENT,
		2025,
		None,
		_ACT_2025,
		LAW,
		(13000, 0, 0),
		(17500, 15, 1950),
		(60000, 25, 3700),
		(None, 35, 9700),
	),
	_table(
		MARRIED_ONE_CHILD,
		2026,
		2026,
		_ACT_2026,
		LAW,
		(17500, 0, 0),
		(26500, 15, 2625),
		(60000, 25, 5275),
		(None, 35, 11275),
	),
	_table(
		MARRIED_TWO_CHILDREN,
		2026,
		2026,
		_ACT_2026,
		LAW,
		(22500, 0, 0),
		(32000, 15, 3375),
		(60000, 25, 6575),
		(None, 35, 12575),
	),
	# The Act prints 10,270 in both languages; MTCA's table of 2026 prints 10,275.
	_table(
		PARENT_ONE_CHILD,
		2026,
		2026,
		_ACT_2026,
		LAW,
		(14500, 0, 0),
		(21000, 15, 2175),
		(60000, 25, 4275),
		(None, 35, 10270),
	),
	_table(
		PARENT_TWO_CHILDREN,
		2026,
		2026,
		_ACT_2026,
		LAW,
		(18500, 0, 0),
		(25500, 15, 2775),
		(60000, 25, 5325),
		(None, 35, 11325),
	),
	_table(
		MARRIED_ONE_CHILD,
		2027,
		2027,
		_BUDGET_2027,
		ANNOUNCED,
		(20000, 0, 0),
		(30000, 15, 3000),
		(60000, 25, 6000),
		(None, 35, 12000),
	),
	_table(
		MARRIED_TWO_CHILDREN,
		2027,
		2027,
		_BUDGET_2027,
		ANNOUNCED,
		(30000, 0, 0),
		(41000, 15, 4500),
		(60000, 25, 8600),
		(None, 35, 14600),
	),
	_table(
		PARENT_ONE_CHILD,
		2027,
		2027,
		_BUDGET_2027,
		ANNOUNCED,
		(16000, 0, 0),
		(24500, 15, 2400),
		(60000, 25, 4850),
		(None, 35, 10850),
	),
	_table(
		PARENT_TWO_CHILDREN,
		2027,
		2027,
		_BUDGET_2027,
		ANNOUNCED,
		(24000, 0, 0),
		(33500, 15, 3600),
		(60000, 25, 6950),
		(None, 35, 12950),
	),
	_table(
		MARRIED_ONE_CHILD,
		2028,
		None,
		_BUDGET_2027,
		ANNOUNCED,
		(22500, 0, 0),
		(33500, 15, 3375),
		(60000, 25, 6725),
		(None, 35, 12725),
	),
	_table(
		MARRIED_TWO_CHILDREN,
		2028,
		None,
		_BUDGET_2027,
		ANNOUNCED,
		(37000, 0, 0),
		(50000, 15, 5550),
		(60000, 25, 10550),
		(None, 35, 16550),
	),
	_table(
		PARENT_ONE_CHILD,
		2028,
		None,
		_BUDGET_2027,
		ANNOUNCED,
		(18000, 0, 0),
		(28000, 15, 2700),
		(60000, 25, 5500),
		(None, 35, 11500),
	),
	_table(
		PARENT_TWO_CHILDREN,
		2028,
		None,
		_BUDGET_2027,
		ANNOUNCED,
		(30000, 0, 0),
		(42000, 15, 4500),
		(60000, 25, 8700),
		(None, 35, 14700),
	),
)

_GUIDE_26A = "MTCA, Completing your tax return, section 26A"

# The tables of Act XV of 2016 raise the tax by 90, 105 and 120 at one band limit each; the return removes the step.
BRACKET_REBATES = (
	BracketRebate(SINGLE, 2020, 2024, 19500, 19620, 17440, _GUIDE_26A, MTCA_GUIDE),
	BracketRebate(PARENT, 2020, 2024, 21200, 21340, 19055, _GUIDE_26A, MTCA_GUIDE),
	BracketRebate(MARRIED, 2020, 2024, 28700, 28860, 25550, _GUIDE_26A, MTCA_GUIDE),
)

# Provisional tax (S.L. 372.18): percentages of the benchmark (rule 5), due month and day in the basis year
# (rule 4(1)), and the number of basis years between the benchmark year and the payment year (rule 2).
PT_SHARES = (20, 30, 50)
PT_DUE = ((4, 30), (8, 31), (12, 21))
PT_BENCHMARK_OFFSET = 2
PT_SOURCE = "S.L. 372.18 rules 2 to 6"

# Tax return date and tax settlement date in the year of assessment (S.L. 372.16 rules 2(c)(ii) and 5(b)).
SETTLEMENT = (6, 30)

# Additional tax on provisional tax not paid by its due date, keyed to the first day of each month of delay.
PT_ADDITIONAL_TAX = (
	MonthlyRate(date(2000, 1, 1), date(2019, 12, 31), Decimal("1"), "S.L. 372.18 rule 14(1)"),
	MonthlyRate(
		date(2020, 1, 1), date(2022, 5, 31), Decimal("0.33"), "S.L. 372.18 rule 14(1), first proviso"
	),
	MonthlyRate(date(2022, 6, 1), None, Decimal("0.6"), "S.L. 372.18 rule 14(1), second proviso"),
)
# Share of the additional tax remitted on the provisional tax above the final tax (rule 14(1), last proviso).
PT_ADDITIONAL_TAX_REDUCTION = Decimal("0.9")

# Interest on tax not paid by the settlement date (ITMA art. 44(2A)), keyed to the date the tax is payable.
TAX_INTEREST = (
	MonthlyRate(date(2020, 1, 1), date(2022, 8, 30), Decimal("0.33"), "S.L. 372.28 rule 2, first proviso"),
	MonthlyRate(date(2022, 8, 31), None, Decimal("0.6"), "S.L. 372.28 rule 2, second proviso"),
)

# Class 2: percentage of the annual net earnings in category SB, and the divisor giving the weekly rate.
CLASS2_PERCENT = 15
CLASS2_WEEKS = 52
# Net earnings above which a person is self-occupied (SSA art. 2).
CLASS2_THRESHOLD = 910
# Due month and day of the periods January to April, May to August and September to December as demanded by MTCA;
# SSA art. 11 names the last day of April, August and December.
CLASS2_DUE = ((4, 30), (8, 31), (12, 21))

_SCHEDULE = "SSA Tenth Schedule Part III"
_MTCA_CLASS2 = "MTCA, Class 2 Social Security Contribution Rates"


def _class2(year: int, source: str, status: str, *values: str) -> Class2Table:
	return Class2Table(year, *(Decimal(v) for v in values), source, status)


CLASS2_TABLES = (
	_class2(
		2021, f"{_SCHEDULE}, L.N. 331 of 2021", LAW, "31.03", "10757", "19362", "55.85", "25258", "72.86"
	),
	_class2(
		2022, f"{_SCHEDULE}, L.N. 232 of 2023", LAW, "31.29", "10848", "19706.90", "56.85", "25986", "74.96"
	),
	_class2(
		2023,
		f"{_SCHEDULE}, L.N. 257 of 2023",
		LAW,
		"32.78",
		"11362.80",
		"20423.72",
		"58.91",
		"26831.48",
		"77.40",
	),
	_class2(
		2024, f"{_SCHEDULE}, L.N. 10 of 2025", LAW, "34.70", "12028.92", "22000", "63.46", "27679.09", "79.84"
	),
	_class2(2025, _MTCA_CLASS2, MTCA_TABLE, "35.48", "12301.39", "23499.99", "67.79", "28303.35", "81.64"),
	_class2(2026, _MTCA_CLASS2, MTCA_TABLE, "36.18", "12543.72", "25499.99", "73.56", "29083.35", "83.89"),
	_class2(2027, _MTCA_CLASS2, MTCA_TABLE, "37.15", "12877.04", "28000.00", "80.77", "29863.36", "86.14"),
)

# Addition on Class 2 contributions not paid by their due date, keyed to the first day of each month of delay: the
# further contribution of SSA art. 116(1)(c), from 2026 the interest of ITMA art. 44(2A).
CLASS2_LATE = (
	MonthlyRate(date(2000, 1, 3), date(2025, 12, 31), Decimal("1"), "SSA art. 116(1)(c)"),
	MonthlyRate(
		date(2026, 1, 1), None, Decimal("0.6"), "SSA art. 116(1) proviso (Act III of 2026); S.L. 372.28"
	),
)


def rate_table(category: str, basis_year: int) -> RateTable:
	for table in RATE_TABLES:
		if (
			table.category == category
			and table.first <= basis_year
			and (table.last is None or basis_year <= table.last)
		):
			return table
	raise NotCovered(f"No rate table '{category}' covers basis year {basis_year}")


def bracket_rebate(category: str, basis_year: int) -> BracketRebate | None:
	for rebate in BRACKET_REBATES:
		if rebate.category == category and rebate.first <= basis_year <= rebate.last:
			return rebate
	return None


def class2_table(year: int) -> Class2Table:
	for table in CLASS2_TABLES:
		if table.year == year:
			return table
	raise NotCovered(f"No Class 2 table covers contribution year {year}")


def monthly_rate(versions: tuple[MonthlyRate, ...], on: date) -> MonthlyRate:
	for version in versions:
		if version.first <= on and (version.last is None or on <= version.last):
			return version
	raise NotCovered(f"No monthly rate covers {on.isoformat()}")


def review_warning(year: int) -> str | None:
	"""Warning text when the year lies after the last reviewed year, else None."""
	if year > REVIEWED_UP_TO:
		return (
			f"The Maltese income tax, provisional tax and Class 2 rules of this app were reviewed up to {REVIEWED_UP_TO}; "
			f"{year} is not yet covered by a review."
		)
	return None
