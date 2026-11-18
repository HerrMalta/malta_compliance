"""Provisional tax of a basis year under the Payment of Provisional Tax (P.T.) Rules, S.L. 372.18: the benchmark
from the self-assessment of the basis year two years earlier, three instalments of 20%, 30% and 50% rounded to the
euro, the limit of a P.T. Reduction Form, and the additional tax on late instalments (docs/income-tax.md). No
Frappe imports.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from malta_compliance.tax import late, rules


@dataclass(frozen=True)
class Instalment:
	"""One P.T. payment: number 1 to 3, due date, percentage of the benchmark and amount in whole euro."""

	number: int
	due: date
	share: int
	amount: int


def benchmark_year(basis_year: int) -> int:
	"""Basis year of the benchmark year of assessment: the last one with a return due before the payment year."""
	return basis_year - rules.PT_BENCHMARK_OFFSET


def settlement_date(basis_year: int) -> date:
	"""Tax settlement date of the year of assessment following the basis year."""
	return date(basis_year + 1, *rules.SETTLEMENT)


def benchmark(tax_due, tax_at_source=0) -> int:
	"""P.T. benchmark of rule 6(1): the tax payable in the self-assessment of the benchmark year plus the
	provisional tax credited in it, that is the tax after credits less the tax deducted at source."""
	return max(0, int(Decimal(str(tax_due)) - Decimal(str(tax_at_source))))


def instalments(benchmark_amount, basis_year: int, reduced_total=None) -> list[Instalment]:
	"""Instalments of the basis year. reduced_total is the current year liability estimated in a P.T. Reduction
	Form: each instalment is then the lower of its share of the benchmark and the estimate not yet covered by the
	earlier instalments (rule 10(3))."""
	rows, covered = [], 0
	for number, (share, (month, day)) in enumerate(zip(rules.PT_SHARES, rules.PT_DUE, strict=True), start=1):
		amount = int(
			(Decimal(str(benchmark_amount)) * share / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
		)
		if reduced_total is not None:
			amount = min(amount, max(0, int(Decimal(str(reduced_total))) - covered))
		covered += amount
		rows.append(Instalment(number, date(basis_year, month, day), share, amount))
	return rows


def additional_tax(unpaid, due: date, until: date, basis_year: int) -> Decimal:
	"""Additional tax of rule 14 on provisional tax unpaid from `due` until `until`; no month after the tax
	settlement date is counted (rule 14(2))."""
	return late.addition(unpaid, due, until, rules.PT_ADDITIONAL_TAX, settlement_date(basis_year))


def reduction(rows: list[tuple[int, Decimal, Decimal]], final_tax) -> Decimal:
	"""Reduction of the additional tax where the tax of the self-assessment is below the benchmark (rule 14(1),
	last proviso). rows holds per instalment, in order: amount due, amount unpaid, additional tax on the unpaid
	amount. The final tax covers the instalments in order; 90% of the additional tax on the part above it is
	remitted."""
	remaining, total = Decimal(str(final_tax)), Decimal(0)
	for amount, unpaid, added in rows:
		required = min(Decimal(amount), max(Decimal(0), remaining))
		remaining -= required
		excess = Decimal(amount) - required
		if unpaid and excess:
			total += Decimal(str(added)) * min(Decimal(str(unpaid)), excess) / Decimal(str(unpaid))
	return (total * rules.PT_ADDITIONAL_TAX_REDUCTION).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
