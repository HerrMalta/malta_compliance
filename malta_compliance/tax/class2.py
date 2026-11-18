"""Class 2 social security contributions of a self-occupied person for one contribution year (SSA art. 10, 11 and
116, Tenth Schedule Part III): the weekly rate from the net earnings of the preceding calendar year, the Mondays of
the three four-month periods, and the addition on late payment (docs/income-tax.md). Not covered: full-time
farmers, the pro-rata option of part-time self-occupied persons, and persons who are not self-occupied (category
SP). No Frappe imports.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from malta_compliance.tax import late, rules

# Categories of the Tenth Schedule Part III.
SA = "SA"
SB = "SB"
SC = "SC"

# First and last month of the three periods of a contribution year.
PERIODS = ((1, 4), (5, 8), (9, 12))


@dataclass(frozen=True)
class WeeklyRate:
	"""Category and weekly rate of a person for a contribution year."""

	category: str
	rate: Decimal
	table: rules.Class2Table


@dataclass(frozen=True)
class Period:
	"""One four-month period: number 1 to 3, weeks counted, due date and amount due."""

	number: int
	weeks: int
	due: date
	amount: Decimal


def weekly_rate(
	year: int, net_earnings, born_before_1962: bool = False, first_year: bool = False
) -> WeeklyRate:
	"""Weekly rate for the contribution year from the net earnings of the preceding calendar year. first_year is
	the first calendar year of the activity, charged at the lowest rate SA."""
	table = rules.class2_table(year)
	earnings = Decimal(str(net_earnings or 0))
	sb_upper = table.sb_upper_before_1962 if born_before_1962 else table.sb_upper_from_1962
	if first_year or earnings <= table.sa_upper:
		return WeeklyRate(SA, table.sa_rate, table)
	if earnings <= sb_upper:
		rate = (earnings * rules.CLASS2_PERCENT / 100 / rules.CLASS2_WEEKS).quantize(
			Decimal("0.01"), rounding=ROUND_HALF_UP
		)
		return WeeklyRate(SB, rate, table)
	return WeeklyRate(SC, table.sc_rate_before_1962 if born_before_1962 else table.sc_rate_from_1962, table)


def mondays(first: date, last: date) -> int:
	"""Number of Mondays from first to last, both included; a contribution week is counted by its Monday."""
	if last < first:
		return 0
	first_monday = first + timedelta(days=(7 - first.weekday()) % 7)
	return 0 if first_monday > last else (last - first_monday).days // 7 + 1


def periods(year: int, rate, active_from: date | None = None, active_to: date | None = None) -> list[Period]:
	"""The three periods of the year at the weekly rate. active_from and active_to limit the weeks to the time of
	the self-occupation."""
	rows = []
	for number, ((first_month, last_month), (due_month, due_day)) in enumerate(
		zip(PERIODS, rules.CLASS2_DUE, strict=True), start=1
	):
		first = date(year, first_month, 1)
		last = (
			date(year + 1, 1, 1) - timedelta(days=1)
			if last_month == 12
			else date(year, last_month + 1, 1) - timedelta(days=1)
		)
		weeks = mondays(
			max(first, active_from) if active_from else first, min(last, active_to) if active_to else last
		)
		rows.append(Period(number, weeks, date(year, due_month, due_day), Decimal(str(rate)) * weeks))
	return rows


def late_addition(unpaid, due: date, until: date) -> Decimal:
	"""Addition on contributions unpaid from `due` until `until` (SSA art. 116(1))."""
	return late.addition(unpaid, due, until, rules.CLASS2_LATE)
