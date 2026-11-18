"""Monthly additions on amounts paid after their due date: additional tax on provisional tax, the further
contribution or interest on Class 2 contributions. The months are counted as in the MTCA booklet "Provisional Tax
and Social Security Contributions": from the calendar month after the month of the due date, each month or part of a
month in which the amount is unpaid (docs/income-tax.md, "Readings"). No Frappe imports.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from malta_compliance.tax import rules


def months_of_delay(due: date, until: date, last: date | None = None) -> list[date]:
	"""First days of the months counted for an amount due on `due` and unpaid until `until`; no month after the
	month of `last` is counted."""
	if last and until > last:
		until = last
	months, year, month = [], due.year, due.month
	while True:
		year, month = (year + 1, 1) if month == 12 else (year, month + 1)
		if (year, month) > (until.year, until.month):
			return months
		months.append(date(year, month, 1))


def addition(
	amount, due: date, until: date, versions: tuple[rules.MonthlyRate, ...], last: date | None = None
) -> Decimal:
	"""Addition on `amount`, each month at the rate in force on its first day."""
	total = sum(
		(Decimal(str(amount)) * rules.monthly_rate(versions, month).percent / 100)
		for month in months_of_delay(due, until, last)
	)
	return Decimal(total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
