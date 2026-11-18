"""Income tax of a resident individual or married couple for one basis year, computed as in the Maltese return of
income: boxes in whole euro, for a married couple the joint computation at the married rates beside the separate
computation of each spouse, and the lower tax charged (ITA art. 49, 50 and 56(1); docs/income-tax.md). Class 2
contributions of the taxpayer are not a deduction. No Frappe imports.
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_HALF_DOWN, Decimal

from malta_compliance.tax import rules

# Tax status of the return.
SINGLE = "Single"
MARRIED = "Married"
SINGLE_PARENT = "Single Parent"

# Computation of a married couple.
JOINT = "Joint"
SEPARATE = "Separate"


@dataclass(frozen=True)
class TaxInput:
	"""Figures of one return. Earned income is the income of return boxes 1 to 4 (trade, employment, pension), per
	person; other income and deductions are boxes 15 and 22. children counts the qualifying children of ITA
	art. 56(1): 0, 1, or 2 for two or more. child_tables is the nationality or residence condition of the tables
	for taxpayers with children."""

	basis_year: int
	status: str
	children: int = 0
	child_tables: bool = True
	earned_self: Decimal = Decimal(0)
	earned_spouse: Decimal = Decimal(0)
	other_income: Decimal = Decimal(0)
	deductions: Decimal = Decimal(0)
	tax_credits: Decimal = Decimal(0)
	tax_at_source: Decimal = Decimal(0)
	provisional_tax: Decimal = Decimal(0)


@dataclass(frozen=True)
class Computation:
	"""Tax on one chargeable income under one rate table: return boxes 25, 26 and 26A."""

	chargeable_income: int
	table: rules.RateTable
	tax: int
	rebate: int
	rebate_rule: rules.BracketRebate | None

	@property
	def tax_after_rebate(self) -> int:
		"""Tax less the rebate for certain income brackets."""
		return self.tax - self.rebate


@dataclass(frozen=True)
class TaxResult:
	"""Result of a return. computation is JOINT or SEPARATE for a married couple, else None. balance is positive for
	tax underpaid and negative for tax overpaid (box 42)."""

	earned_self: int
	earned_spouse: int
	other_net: int
	single: Computation | None
	separate_self: Computation | None
	separate_spouse: Computation | None
	joint: Computation | None
	computation: str | None
	tax_charged: int
	tax_credits: int
	tax_due: int
	payments: Decimal
	balance: Decimal

	def computations(self) -> list[Computation]:
		"""Computations used for the tax charged."""
		if self.single:
			return [self.single]
		if self.computation == JOINT:
			return [self.joint]
		return [self.separate_self, self.separate_spouse]


def whole_euro(amount) -> int:
	"""Income box of the return: the fraction of a euro is dropped."""
	return int(Decimal(str(amount)).quantize(Decimal(1), rounding=ROUND_DOWN))


def deduction_euro(amount) -> int:
	"""Deduction box of the return: rounded up to one euro."""
	return int(Decimal(str(amount)).quantize(Decimal(1), rounding=ROUND_CEILING))


def tax_euro(amount) -> int:
	"""Tax box of the return: a fraction up to 50 cents is dropped, a higher one is rounded up."""
	return int(Decimal(str(amount)).quantize(Decimal(1), rounding=ROUND_HALF_DOWN))


def tax_on(chargeable_income: int, table: rules.RateTable, basis_year: int) -> Computation:
	"""Tax and rebate on one chargeable income under one table; an income equal to a band limit falls into the
	lower band, and a negative income is taxed as nil."""
	income = max(0, chargeable_income)
	band = next(b for b in table.bands if b.upper is None or income <= b.upper)
	tax = max(0, tax_euro(Decimal(income) * band.rate / 100 - band.subtract))
	rebate_rule = rules.bracket_rebate(table.category, basis_year)
	rebate = 0
	if rebate_rule and rebate_rule.above < income < rebate_rule.below:
		rebate = max(0, rebate_rule.net - (income - tax))
	return Computation(chargeable_income, table, tax, rebate, rebate_rule if rebate else None)


def _first_covered(basis_year: int, *categories: str) -> rules.RateTable:
	"""The table of the first category covering the basis year; the last category has to cover it."""
	for category in categories[:-1]:
		try:
			return rules.rate_table(category, basis_year)
		except rules.NotCovered:
			continue
	return rules.rate_table(categories[-1], basis_year)


def individual_table(inp: TaxInput) -> rules.RateTable:
	"""Table of ITA art. 56(1)(b) for a single person or a spouse in the separate computation."""
	if not inp.children:
		return rules.rate_table(rules.SINGLE, inp.basis_year)
	if inp.child_tables:
		category = rules.PARENT_ONE_CHILD if inp.children == 1 else rules.PARENT_TWO_CHILDREN
		return _first_covered(inp.basis_year, category, rules.PARENT)
	return rules.rate_table(rules.PARENT, inp.basis_year)


def joint_table(inp: TaxInput) -> rules.RateTable:
	"""Table of ITA art. 56(1)(a) for the joint computation of a married couple."""
	if inp.children and inp.child_tables:
		category = rules.MARRIED_ONE_CHILD if inp.children == 1 else rules.MARRIED_TWO_CHILDREN
		return _first_covered(inp.basis_year, category, rules.MARRIED)
	return rules.rate_table(rules.MARRIED, inp.basis_year)


def compute(inp: TaxInput) -> TaxResult:
	"""Tax of the return. Married: other income less deductions goes to the spouse with the higher earned income, to
	the first spouse where both are equal (return boxes 24e and 24f); single parent: the married table, unless a
	table for parents with children gives less tax (ITA art. 56(1)(b)(iii))."""
	earned_self = whole_euro(inp.earned_self)
	earned_spouse = whole_euro(inp.earned_spouse) if inp.status == MARRIED else 0
	other_net = whole_euro(inp.other_income) - deduction_euro(inp.deductions)
	single = separate_self = separate_spouse = joint = computation = None
	if inp.status == MARRIED:
		to_self = earned_self >= earned_spouse
		table = individual_table(inp)
		separate_self = tax_on(earned_self + (other_net if to_self else 0), table, inp.basis_year)
		separate_spouse = tax_on(earned_spouse + (0 if to_self else other_net), table, inp.basis_year)
		joint = tax_on(earned_self + earned_spouse + other_net, joint_table(inp), inp.basis_year)
		separate_tax = separate_self.tax_after_rebate + separate_spouse.tax_after_rebate
		computation = JOINT if joint.tax_after_rebate <= separate_tax else SEPARATE
		tax_charged = min(joint.tax_after_rebate, separate_tax)
	elif inp.status == SINGLE_PARENT:
		income = earned_self + other_net
		single = tax_on(income, rules.rate_table(rules.MARRIED, inp.basis_year), inp.basis_year)
		if inp.children and inp.child_tables:
			with_children = tax_on(income, individual_table(inp), inp.basis_year)
			if with_children.tax_after_rebate < single.tax_after_rebate:
				single = with_children
		tax_charged = single.tax_after_rebate
	else:
		single = tax_on(earned_self + other_net, individual_table(inp), inp.basis_year)
		tax_charged = single.tax_after_rebate
	credits = tax_euro(inp.tax_credits)
	tax_due = max(0, tax_charged - credits)
	payments = Decimal(str(inp.tax_at_source)) + Decimal(str(inp.provisional_tax))
	return TaxResult(
		earned_self=earned_self,
		earned_spouse=earned_spouse,
		other_net=other_net,
		single=single,
		separate_self=separate_self,
		separate_spouse=separate_spouse,
		joint=joint,
		computation=computation,
		tax_charged=tax_charged,
		tax_credits=credits,
		tax_due=tax_due,
		payments=payments,
		balance=Decimal(tax_due) - payments,
	)
