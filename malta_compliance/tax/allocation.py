"""Allocation of payments to amounts due in order, and the monthly addition on the parts paid late or unpaid. Used
for provisional tax (S.L. 372.18 rule 13(1): a payment discharges the instalments in the order they fall due) and
for Class 2 contributions. No Frappe imports.
"""

from collections.abc import Callable
from datetime import date
from decimal import Decimal


def allocate(
	dues: list, payments: list[tuple[date, Decimal]]
) -> tuple[list[list[tuple[date, Decimal]]], Decimal]:
	"""Applies the payments in date order to the amounts due in list order. Returns per amount due the parts paid
	with their dates, and the excess of the payments over the total due."""
	parts = [[] for _due in dues]
	open_amounts = [Decimal(str(due)) for due in dues]
	excess = Decimal(0)
	for paid_on, amount in sorted(payments, key=lambda p: p[0]):
		rest = Decimal(str(amount))
		for index, open_amount in enumerate(open_amounts):
			if rest <= 0:
				break
			part = min(rest, open_amount)
			if part > 0:
				parts[index].append((paid_on, part))
				open_amounts[index] -= part
				rest -= part
		excess += max(rest, Decimal(0))
	return parts, excess


def paid(parts: list[tuple[date, Decimal]]) -> Decimal:
	"""Total of the parts paid."""
	return sum((amount for _paid_on, amount in parts), Decimal(0))


def late_parts(
	due_amount, due: date, parts: list[tuple[date, Decimal]], today: date, addition: Callable
) -> list[tuple[Decimal, Decimal]]:
	"""(amount, addition) of each part of one amount due, in the order of payment, with the unpaid rest last. The
	addition of a part runs from the due date to its payment, that of the rest until today; addition(amount, due,
	until) computes it."""
	rows = [(amount, addition(amount, due, paid_on)) for paid_on, amount in parts]
	rest = Decimal(str(due_amount)) - paid(parts)
	if rest > 0:
		rows.append((rest, addition(rest, due, today)))
	return rows


def late_addition(rows: list[tuple[Decimal, Decimal]]) -> Decimal:
	"""Total addition of the parts returned by late_parts."""
	return sum((added for _amount, added in rows), Decimal(0))
