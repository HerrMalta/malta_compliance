"""Tests of the rule register and the computations of income tax, provisional tax and Class 2 contributions
(docs/income-tax.md). All figures are invented. The modules under test import no Frappe, so the tests also run
without a site.

Run: bench --site <test site> run-tests --module malta_compliance.tests.test_tax_rules
  or: python -m unittest malta_compliance.tests.test_tax_rules
"""

import unittest
from datetime import date
from decimal import Decimal

from malta_compliance.tax import allocation, class2, income_tax, late, provisional_tax, rules
from malta_compliance.tax.income_tax import JOINT, MARRIED, SEPARATE, SINGLE, SINGLE_PARENT, TaxInput

# Rise of the tax at a band limit, for the tables that are not continuous there.
STEPS = {
	(rules.SINGLE, 2020, 19500): 90,
	(rules.PARENT, 2020, 21200): 105,
	(rules.MARRIED, 2020, 28700): 120,
	(rules.PARENT_ONE_CHILD, 2026, 60000): 5,
}


def tax(basis_year: int, status: str = SINGLE, **amounts) -> income_tax.TaxResult:
	return income_tax.compute(TaxInput(basis_year=basis_year, status=status, **amounts))


def pt_addition(amount, due: date, until: date) -> Decimal:
	"""Additional tax on provisional tax of basis year 2025."""
	return provisional_tax.additional_tax(amount, due, until, 2025)


class TestRateTables(unittest.TestCase):
	def test_tables_are_continuous_except_known_steps(self):
		for table in rules.RATE_TABLES:
			for lower, upper in zip(table.bands, table.bands[1:], strict=False):
				at_limit = Decimal(lower.upper) * lower.rate / 100 - lower.subtract
				above = Decimal(lower.upper) * upper.rate / 100 - upper.subtract
				expected = STEPS.get((table.category, table.first, lower.upper), 0)
				self.assertEqual(
					above - at_limit, expected, f"{table.category} {table.first} at {lower.upper}"
				)

	def test_each_category_has_one_table_per_year(self):
		for year in range(2020, 2031):
			for category in (rules.SINGLE, rules.MARRIED, rules.PARENT):
				matching = [
					t
					for t in rules.RATE_TABLES
					if t.category == category and t.first <= year and (t.last is None or year <= t.last)
				]
				self.assertEqual(len(matching), 1, f"{category} {year}")

	def test_child_tables_start_with_basis_year_2026(self):
		with self.assertRaises(rules.NotCovered):
			rules.rate_table(rules.MARRIED_ONE_CHILD, 2025)
		self.assertEqual(rules.rate_table(rules.MARRIED_ONE_CHILD, 2026).status, rules.LAW)
		self.assertEqual(rules.rate_table(rules.PARENT_TWO_CHILDREN, 2027).status, rules.ANNOUNCED)
		self.assertEqual(rules.rate_table(rules.PARENT_TWO_CHILDREN, 2030).bands[0].upper, 30000)

	def test_years_before_2020_are_not_covered(self):
		with self.assertRaises(rules.NotCovered):
			tax(2019, earned_self=20000)

	def test_review_warning(self):
		self.assertIsNone(rules.review_warning(rules.REVIEWED_UP_TO))
		self.assertIn(str(rules.REVIEWED_UP_TO + 1), rules.review_warning(rules.REVIEWED_UP_TO + 1))


class TestIncomeTax(unittest.TestCase):
	def test_tax_is_rounded_at_fifty_cents(self):
		self.assertEqual(tax(2021, earned_self=13010).tax_charged, 586, "586.50 is rounded down")
		self.assertEqual(tax(2021, earned_self=13004).tax_charged, 586, "585.60 is rounded up")
		self.assertEqual(tax(2021, earned_self=13002).tax_charged, 585, "585.30 is rounded down")

	def test_income_boxes_drop_cents_and_deductions_round_up(self):
		result = tax(
			2024,
			earned_self=Decimal("30000.99"),
			other_income=Decimal("1000.99"),
			deductions=Decimal("300.40"),
		)
		self.assertEqual(result.earned_self, 30000)
		self.assertEqual(result.other_net, 699)
		self.assertEqual(result.single.chargeable_income, 30699)

	def test_profit_rounds_each_account_before_the_sum(self):
		lines = [Decimal("4321.40"), Decimal("-1234.60"), Decimal("-210.50")]
		self.assertEqual(income_tax.profit_euro(lines), 2875, "4,321 less 1,235 less 211")
		self.assertEqual(income_tax.whole_euro(sum(lines)), 2876, "2,876.30 without the cents")
		self.assertEqual([income_tax.account_euro(a) for a in (0.5, -0.5, 7.49, -7.49)], [1, -1, 7, -7])
		self.assertEqual(income_tax.profit_euro([]), 0)

	def test_married_couple_takes_the_lower_of_joint_and_separate(self):
		separate = tax(2022, MARRIED, earned_self=30000, earned_spouse=5000)
		self.assertEqual(separate.joint.tax, 4845)
		self.assertEqual((separate.separate_self.tax, separate.separate_spouse.tax), (4775, 0))
		self.assertEqual((separate.computation, separate.tax_charged), (SEPARATE, 4775))
		joint = tax(2023, MARRIED, earned_self=25000)
		self.assertEqual((joint.joint.tax, joint.separate_self.tax), (2225, 3525))
		self.assertEqual((joint.computation, joint.tax_charged), (JOINT, 2225))

	def test_other_income_goes_to_the_spouse_with_the_higher_earned_income(self):
		result = tax(
			2024,
			MARRIED,
			earned_self=20000,
			earned_spouse=22000,
			other_income=1000,
			deductions=Decimal("300.40"),
		)
		self.assertEqual(result.separate_self.chargeable_income, 20000)
		self.assertEqual(result.separate_spouse.chargeable_income, 22699)
		self.assertEqual((result.separate_self.tax, result.separate_spouse.tax), (2275, 2950))
		self.assertEqual(result.joint.tax, 6770)
		self.assertEqual((result.computation, result.tax_charged), (SEPARATE, 5225))
		equal = tax(2024, MARRIED, earned_self=20000, earned_spouse=20000, other_income=500)
		self.assertEqual(equal.separate_self.chargeable_income, 20500)

	def test_bracket_rebate_up_to_basis_year_2024(self):
		inside = tax(2024, earned_self=19560)
		self.assertEqual((inside.single.tax, inside.single.rebate, inside.tax_charged), (2165, 45, 2120))
		self.assertEqual(tax(2024, earned_self=19500).single.rebate, 0)
		self.assertEqual(tax(2024, earned_self=19620).single.rebate, 0)
		married = tax(2024, MARRIED, earned_self=28780)
		self.assertEqual((married.joint.tax, married.joint.rebate), (3290, 60))
		parent = tax(2023, children=1, earned_self=21300)
		self.assertEqual((parent.single.tax, parent.single.rebate), (2275, 30))
		self.assertEqual(tax(2025, earned_self=19560).single.rebate, 0)

	def test_tables_from_basis_year_2025(self):
		self.assertEqual(tax(2025, earned_self=50000).tax_charged, 9100)
		self.assertEqual(tax(2025, MARRIED, earned_self=80000).joint.tax, 17450)
		self.assertEqual(tax(2025, children=1, earned_self=20000).single.table.category, rules.PARENT)

	def test_tables_for_taxpayers_with_children_from_basis_year_2026(self):
		with_child = tax(2026, MARRIED, children=1, earned_self=40000)
		self.assertEqual(
			(with_child.joint.table.category, with_child.joint.tax), (rules.MARRIED_ONE_CHILD, 4725)
		)
		without_condition = tax(2026, MARRIED, children=1, child_tables=False, earned_self=40000)
		self.assertEqual(
			(without_condition.joint.table.category, without_condition.joint.tax), (rules.MARRIED, 5450)
		)
		self.assertEqual(without_condition.separate_self.table.category, rules.PARENT)
		self.assertEqual(tax(2026, children=1, earned_self=70000).tax_charged, 14230)
		announced = tax(2027, children=2, earned_self=30000)
		self.assertEqual((announced.tax_charged, announced.single.table.status), (900, rules.ANNOUNCED))

	def test_single_parent_takes_the_lower_of_married_and_parent_tables(self):
		result = tax(2026, SINGLE_PARENT, children=2, earned_self=30000)
		self.assertEqual(
			(result.single.table.category, result.tax_charged), (rules.PARENT_TWO_CHILDREN, 2175)
		)
		earlier = tax(2024, SINGLE_PARENT, children=1, earned_self=30000)
		self.assertEqual((earlier.single.table.category, earlier.tax_charged), (rules.MARRIED, 3595))

	def test_credits_and_payments(self):
		result = tax(
			2022,
			MARRIED,
			earned_self=30000,
			earned_spouse=5000,
			tax_credits=500,
			tax_at_source=1000,
			provisional_tax=2000,
		)
		self.assertEqual((result.tax_charged, result.tax_due, result.balance), (4775, 4275, Decimal(1275)))
		overpaid = tax(2022, earned_self=10000, provisional_tax=300)
		self.assertEqual((overpaid.tax_due, overpaid.balance), (135, Decimal(-165)))
		self.assertEqual(tax(2022, earned_self=10000, tax_credits=900).tax_due, 0)

	def test_a_loss_gives_no_tax(self):
		result = tax(2025, MARRIED, earned_self=-4000, earned_spouse=20000)
		self.assertEqual(result.separate_self.tax, 0)
		self.assertEqual(result.joint.chargeable_income, 16000)


class TestProvisionalTax(unittest.TestCase):
	def test_benchmark_year_and_benchmark(self):
		self.assertEqual(provisional_tax.benchmark_year(2025), 2023)
		self.assertEqual(provisional_tax.benchmark(1200, 200), 1000)
		self.assertEqual(provisional_tax.benchmark(150, 400), 0)

	def test_instalments(self):
		rows = provisional_tax.instalments(1234, 2026)
		self.assertEqual([r.amount for r in rows], [247, 370, 617])
		self.assertEqual([r.due for r in rows], [date(2026, 4, 30), date(2026, 8, 31), date(2026, 12, 21)])
		self.assertEqual([r.amount for r in provisional_tax.instalments(1235, 2026)], [247, 371, 618])
		self.assertEqual([r.amount for r in provisional_tax.instalments(0, 2026)], [0, 0, 0])

	def test_reduction_form_limits_the_instalments_due_after_it(self):
		self.assertEqual([r.amount for r in provisional_tax.instalments(1000, 2026, 800)], [200, 300, 300])
		self.assertEqual([r.amount for r in provisional_tax.instalments(1000, 2026, 150)], [150, 0, 0])
		filed = date(2026, 7, 10)
		unpaid = provisional_tax.instalments(1000, 2026, 150, filed, lambda until: Decimal(0))
		self.assertEqual([r.amount for r in unpaid], [200, 150, 150])
		paid_in_august = provisional_tax.instalments(
			1000, 2026, 150, filed, lambda until: Decimal(150) if until >= date(2026, 8, 31) else Decimal(0)
		)
		self.assertEqual([r.amount for r in paid_in_august], [200, 150, 0])

	def test_additional_tax_counts_the_months_after_the_due_month(self):
		first_due = date(2025, 4, 30)
		self.assertEqual(pt_addition(400, first_due, date(2025, 4, 30)), Decimal("0.00"))
		self.assertEqual(pt_addition(400, first_due, date(2025, 5, 10)), Decimal("2.40"))
		self.assertEqual(pt_addition(400, first_due, date(2027, 1, 1)), Decimal("33.60"))
		third_due = date(2025, 12, 21)
		self.assertEqual(pt_addition(1000, third_due, date(2025, 12, 28)), Decimal("0.00"))
		self.assertEqual(pt_addition(1000, third_due, date(2026, 8, 15)), Decimal("36.00"))

	def test_additional_tax_rate_by_month(self):
		self.assertEqual(rules.monthly_rate(rules.PT_ADDITIONAL_TAX, date(2019, 12, 1)).percent, Decimal("1"))
		self.assertEqual(
			rules.monthly_rate(rules.PT_ADDITIONAL_TAX, date(2021, 3, 1)).percent, Decimal("0.33")
		)
		self.assertEqual(
			rules.monthly_rate(rules.PT_ADDITIONAL_TAX, date(2022, 6, 1)).percent, Decimal("0.6")
		)
		across = late.addition(1000, date(2022, 4, 30), date(2022, 7, 5), rules.PT_ADDITIONAL_TAX)
		self.assertEqual(across, Decimal("15.30"), "May at 0.33%, June and July at 0.6%")

	def test_remission_on_unpaid_instalments_above_the_final_tax(self):
		unpaid = [
			(400, [(Decimal(400), Decimal("33.60"))]),
			(600, [(Decimal(600), Decimal("36.00"))]),
			(1000, [(Decimal(1000), Decimal("36.00"))]),
		]
		self.assertEqual(provisional_tax.reduction(unpaid, 1000), Decimal("32.40"))
		self.assertEqual(provisional_tax.reduction(unpaid, 2000), Decimal("0.00"))

	def test_remission_on_instalments_paid_late(self):
		instalments = provisional_tax.instalments(2000, 2025)
		paid_on, as_of = date(2026, 3, 15), date(2026, 8, 1)
		rows = [
			(
				i.amount,
				allocation.late_parts(i.amount, i.due, [(paid_on, Decimal(i.amount))], as_of, pt_addition),
			)
			for i in instalments
		]
		additions = [allocation.late_addition(parts) for _amount, parts in rows]
		self.assertEqual(additions, [Decimal("26.40"), Decimal("25.20"), Decimal("18.00")])
		self.assertEqual(provisional_tax.reduction(rows, 1000), Decimal("16.20"))

	def test_remission_counts_the_parts_paid_first_as_the_tax_due(self):
		third = provisional_tax.instalments(2000, 2025)[2]
		parts = allocation.late_parts(
			third.amount, third.due, [(date(2026, 2, 10), Decimal(500))], date(2026, 8, 1), pt_addition
		)
		self.assertEqual(parts, [(Decimal(500), Decimal("6.00")), (Decimal(500), Decimal("18.00"))])
		rows = [(400, []), (600, []), (third.amount, parts)]
		self.assertEqual(provisional_tax.reduction(rows, 1500), Decimal("16.20"))
		self.assertEqual(provisional_tax.reduction(rows, 1250), Decimal("18.90"))


class TestClass2(unittest.TestCase):
	def test_weeks_are_the_mondays_of_each_period(self):
		expected = {
			2021: [17, 18, 17],
			2024: [18, 17, 18],
			2025: [17, 17, 18],
			2026: [17, 18, 17],
			2027: [17, 18, 17],
		}
		for year, weeks in expected.items():
			self.assertEqual([p.weeks for p in class2.periods(year, 1)], weeks, year)

	def test_weekly_rate_by_category(self):
		first = class2.weekly_rate(2021, 50000, first_year=True)
		self.assertEqual((first.category, first.rate), (class2.SA, Decimal("31.03")))
		middle = class2.weekly_rate(2023, 15000)
		self.assertEqual((middle.category, middle.rate), (class2.SB, Decimal("43.27")))
		top = class2.weekly_rate(2025, 100000)
		self.assertEqual((top.category, top.rate), (class2.SC, Decimal("81.64")))
		earlier_birth = class2.weekly_rate(2025, 100000, born_before_1962=True)
		self.assertEqual((earlier_birth.category, earlier_birth.rate), (class2.SC, Decimal("67.79")))
		self.assertEqual(class2.weekly_rate(2025, Decimal("12301.39")).category, class2.SA)
		self.assertEqual(class2.weekly_rate(2025, 12400).rate, Decimal("35.77"))
		self.assertEqual(class2.weekly_rate(2026, -500).category, class2.SA)

	def test_tables_are_continuous_at_their_limits(self):
		cent = Decimal("0.01")
		for table in rules.CLASS2_TABLES:
			for upper, fixed in (
				(table.sa_upper, table.sa_rate),
				(table.sb_upper_before_1962, table.sc_rate_before_1962),
				(table.sb_upper_from_1962, table.sc_rate_from_1962),
			):
				weekly = upper * rules.CLASS2_PERCENT / 100 / rules.CLASS2_WEEKS
				self.assertLessEqual(abs(weekly - fixed), cent, f"{table.year} at {upper}")

	def test_periods_and_partial_year(self):
		rows = class2.periods(2025, Decimal("40.00"))
		self.assertEqual([r.amount for r in rows], [Decimal(680), Decimal(680), Decimal(720)])
		self.assertEqual([r.due for r in rows], [date(2025, 4, 30), date(2025, 8, 31), date(2025, 12, 21)])
		started = class2.periods(2022, Decimal("31.29"), active_from=date(2022, 8, 1))
		self.assertEqual([r.weeks for r in started], [0, 5, 17])
		ended = class2.periods(2023, 1, active_to=date(2023, 2, 28))
		self.assertEqual([r.weeks for r in ended], [9, 0, 0])

	def test_further_contribution_until_2025(self):
		self.assertEqual(class2.late_addition(100, date(2023, 8, 31), date(2023, 11, 15)), Decimal("3.00"))
		self.assertEqual(class2.late_addition(100, date(2023, 8, 31), date(2023, 8, 31)), Decimal("0.00"))

	def test_interest_from_2026_at_the_rate_for_the_date_payable(self):
		self.assertEqual(class2.late_addition(100, date(2026, 4, 30), date(2026, 6, 1)), Decimal("1.20"))
		self.assertEqual(class2.late_addition(100, date(2025, 12, 21), date(2026, 2, 1)), Decimal("1.20"))
		across = class2.late_addition(100, date(2021, 4, 30), date(2026, 2, 10))
		self.assertEqual(across, Decimal("56.66"), "56 months at 1%, two months at 0.33%")

	def test_years_outside_the_tables_are_not_covered(self):
		with self.assertRaises(rules.NotCovered):
			class2.weekly_rate(2020, 10000)


class TestAllocation(unittest.TestCase):
	def test_payments_discharge_the_amounts_due_in_order(self):
		early, later = date(2026, 4, 20), date(2026, 9, 5)
		parts, excess = allocation.allocate([200, 300, 500], [(later, Decimal(100)), (early, Decimal(250))])
		self.assertEqual(parts, [[(early, Decimal(200))], [(early, Decimal(50)), (later, Decimal(100))], []])
		self.assertEqual(excess, Decimal(0))
		self.assertEqual(allocation.paid(parts[1]), Decimal(150))
		self.assertEqual(allocation.allocate([100], [(early, Decimal(150))])[1], Decimal(50))

	def test_addition_on_late_parts_and_on_the_unpaid_rest(self):
		due = date(2025, 4, 30)
		paid = [(date(2025, 4, 20), Decimal(100)), (date(2025, 6, 10), Decimal(100))]
		parts = allocation.late_parts(400, due, paid, date(2025, 8, 15), pt_addition)
		self.assertEqual(
			parts,
			[
				(Decimal(100), Decimal("0.00")),
				(Decimal(100), Decimal("1.20")),
				(Decimal(200), Decimal("4.80")),
			],
		)
		self.assertEqual(allocation.late_addition(parts), Decimal("6.00"))
