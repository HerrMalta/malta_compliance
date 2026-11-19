"""Tests of the VAT return and of the settlement amounts (README, "VAT return"). All figures are invented. The
modules under test import no Frappe, so the tests also run without a site.

Run: bench --site <test site> run-tests --module malta_compliance.tests.test_vat_return
  or: python -m unittest malta_compliance.tests.test_vat_return
"""

import unittest
from datetime import date
from fractions import Fraction

from malta_compliance.vat import categories, return_form
from malta_compliance.vat.categories import BASE, CATEGORIES, NO_RETURN_BOX, RATE, TARGETS
from malta_compliance.vat.return_form import LINE, LINES, SUB, Invoice, compute

EU_SERVICES = "VAT Box 3/6 9a/13a EU services reverse charge"
EU_GOODS = "VAT Box 3/6 9/13 EU goods for resale reverse charge"
EU_CAPITAL = "VAT Box 3/6 10/14 EU capital goods reverse charge"
NON_EU = "VAT Box 4/7 11/15 Non-EU services reverse charge"
PRIVATE = "VAT Box 3/6 EU goods for private use not deductible"
OVERHEADS = "VAT Box 31/37 Malta services and overheads 18%"
CAPITAL = "VAT Box 30/36 Malta capital goods 18%"
EU_CUSTOMER = "VAT Box 1 EU business customer liable"
OUTSIDE_MALTA = "VAT Box 2 Supply outside Malta"
MALTA_18 = "VAT Box 18/23 Malta 18%"
EXEMPT = "VAT Box 20 Exempt with credit or export"

_numbers = iter(range(1, 1000))


def sale(category: str, base: int, vat: int = 0, rate: float = 0) -> Invoice:
	return Invoice(
		"Sales Invoice", f"SINV-{next(_numbers)}", "2030-02-01", "Customer", category, base, vat, 0, (rate,)
	)


def purchase(category: str, base: int, output: int = 0, input_vat: int = 0, rates=(18,)) -> Invoice:
	return Invoice(
		"Purchase Invoice",
		f"PINV-{next(_numbers)}",
		"2030-02-01",
		"Supplier",
		category,
		base,
		output,
		input_vat,
		rates,
	)


def reverse_charge(category: str, base: int, rate: int = 18) -> Invoice:
	vat = base * rate // 100
	return purchase(category, base, vat, vat, (rate, rate))


class TestLayout(unittest.TestCase):
	def test_keys_unique_and_parents_exist(self):
		keys = [line.key for line in LINES]
		self.assertEqual(len(keys), len(set(keys)))
		for line in LINES:
			if line.kind == SUB:
				self.assertIn(line.parent, LINE)
				self.assertEqual(LINE[line.parent].kind, return_form.BOX)

	def test_boxes_of_the_form(self):
		self.assertEqual(LINE["3"].box, "3/6")
		self.assertEqual(LINE["9a"].box, "9a/13a")
		self.assertEqual(LINE["19"].box, "19/24")
		self.assertEqual(LINE["17"].box, "17")
		self.assertEqual(LINE["26"].box, "26")
		self.assertEqual(LINE["42"].box, "42")
		self.assertEqual(LINE["1"].columns, return_form.BASE_ONLY)
		self.assertEqual(LINE["26"].columns, return_form.TAX_ONLY)

	def test_every_category_target_exists(self):
		for title, direction, targets, _rows in CATEGORIES:
			self.assertIn(direction, (categories.SALES, categories.PURCHASE))
			if title == NO_RETURN_BOX:
				self.assertEqual(targets, ())
				continue
			self.assertTrue(targets, title)
			for line_key, selector, part in targets:
				self.assertEqual(LINE[line_key].kind, return_form.BOX, title)
				if selector not in (None, RATE):
					self.assertEqual(LINE[selector].parent, line_key, title)
				if part == BASE:
					self.assertNotEqual(LINE[line_key].columns, return_form.TAX_ONLY, title)
				else:
					self.assertTrue(LINE[line_key].tax_box, title)

	def test_renamed_category(self):
		self.assertIn("VAT Box 19/24 Malta 5%", TARGETS)
		self.assertNotIn("VAT Box 18/24 Malta 5%", TARGETS)
		self.assertEqual(categories.RENAMED["VAT Box 18/24 Malta 5%"][0], "VAT Box 19/24 Malta 5%")


class TestCompute(unittest.TestCase):
	def test_sales_outside_malta(self):
		r = compute([sale(EU_CUSTOMER, 1_000_000), sale(OUTSIDE_MALTA, 50_000), sale(EU_CUSTOMER, -20_000)])
		self.assertEqual(r.base("1"), 980_000)
		self.assertEqual(r.base("2"), 50_000)
		self.assertEqual(r.amounts["5"], [1_030_000, 0])
		self.assertEqual(r.tax("42"), 0)
		self.assertEqual(r.tax("payable"), 0)

	def test_reverse_charge_nets_to_zero(self):
		r = compute(
			[
				reverse_charge(EU_SERVICES, 40_000),
				reverse_charge(EU_CAPITAL, 100_000),
				reverse_charge(NON_EU, 10_000),
			]
		)
		self.assertEqual(r.amounts["3"], [140_000, 25_200])
		self.assertEqual(r.amounts["3_ic"], [140_000, 25_200])
		self.assertEqual(r.amounts["4"], [10_000, 1_800])
		self.assertEqual(r.amounts["4_malta"], [10_000, 1_800])
		self.assertEqual(r.amounts["5"], [150_000, 27_000])
		self.assertEqual(r.amounts["9a"], [40_000, 7_200])
		self.assertEqual(r.amounts["10"], [100_000, 18_000])
		self.assertEqual(r.amounts["10_rc18"], [100_000, 18_000])
		self.assertEqual(r.amounts["11"], [10_000, 1_800])
		self.assertEqual(r.amounts["12"], [150_000, 27_000])
		self.assertEqual(r.amounts["17"], [0, 0])
		self.assertEqual(r.tax("42"), 0)

	def test_private_goods_enter_box_17(self):
		r = compute([purchase(PRIVATE, 20_000, output=3_600, rates=(18, 18))])
		self.assertEqual(r.amounts["3"], [20_000, 3_600])
		self.assertEqual(r.amounts["3_nr18"], [20_000, 3_600])
		self.assertEqual(r.amounts["3_ic"], [0, 0])
		self.assertEqual(r.amounts["12"], [0, 0])
		self.assertEqual(r.amounts["17"], [20_000, 3_600])
		self.assertEqual(r.tax("26"), 3_600)
		self.assertEqual(r.tax("42"), 3_600)
		self.assertEqual(r.tax("payable"), 3_600)
		self.assertEqual(r.tax("excess"), 0)

	def test_domestic_purchases_give_an_excess_credit(self):
		r = compute([sale(MALTA_18, 30_000, 5_400, 18), purchase(OVERHEADS, 100_000, input_vat=18_000)])
		self.assertEqual(r.amounts["18"], [30_000, 5_400])
		self.assertEqual(r.amounts["18_taxable"], [30_000, 5_400])
		self.assertEqual(r.amounts["22"], [30_000, 5_400])
		self.assertEqual(r.tax("26"), 5_400)
		self.assertEqual(r.amounts["31"], [100_000, 18_000])
		self.assertEqual(r.amounts["33"], [100_000, 18_000])
		self.assertEqual(r.tax("42"), -12_600)
		self.assertEqual(r.tax("excess"), 12_600)
		self.assertEqual(r.tax("payable"), -12_600)

	def test_adjustments_and_credit_brought_forward(self):
		invoices = [sale(MALTA_18, 100_000, 18_000, 18), purchase(OVERHEADS, 50_000, input_vat=9_000)]
		r = compute(
			invoices, adjustment_vat_department=500, adjustment_registered_person=200, credit_bf=10_000
		)
		self.assertEqual(r.tax("40"), 500)
		self.assertEqual(r.tax("41"), 200)
		self.assertEqual(r.tax("42"), 18_000 + 500 - 9_000 - 200)
		self.assertEqual(r.tax("bf"), 10_000)
		self.assertEqual(r.tax("payable"), 9_300 - 10_000)
		self.assertEqual(r.tax("excess"), 700)

	def test_sub_line_by_rate(self):
		r = compute(
			[reverse_charge(EU_GOODS, 10_000, 5), purchase(CAPITAL, 20_000, input_vat=1_000, rates=(5,))]
		)
		self.assertEqual(r.amounts["9"], [10_000, 500])
		self.assertEqual(r.amounts["9_rc5"], [10_000, 500])
		self.assertEqual(r.amounts["30"], [20_000, 1_000])
		self.assertEqual(r.amounts["30_5"], [20_000, 1_000])
		self.assertEqual(r.amounts["30_18"], [0, 0])
		self.assertEqual(r.notes, [])

	def test_rate_without_sub_line_counts_in_the_box(self):
		r = compute([reverse_charge(EU_CAPITAL, 10_000, 7)])
		self.assertEqual(r.amounts["10"], [10_000, 700])
		self.assertEqual(r.amounts["10_rc18"], [0, 0])
		self.assertEqual(r.amounts["10_rc5"], [0, 0])
		self.assertEqual(len(r.notes), 1)
		self.assertIn("7%", r.notes[0])

	def test_categories_outside_the_return(self):
		outside = purchase(NO_RETURN_BOX, 5_000, rates=())
		unknown = purchase("", 7_000, rates=())
		other = purchase("Some other category", 9_000, rates=())
		r = compute([outside, unknown, other, sale(EXEMPT, 1_000)])
		self.assertEqual(r.outside, [outside])
		self.assertEqual(r.unknown, [unknown, other])
		self.assertEqual(len(r.counted), 1)
		self.assertEqual(r.base("20"), 1_000)
		self.assertEqual(r.base("33"), 0)

	def test_vat_in_a_box_without_vat_is_noted(self):
		r = compute([sale(EU_CUSTOMER, 10_000, 1_800, 18)])
		self.assertEqual(r.amounts["1"], [10_000, 0])
		self.assertEqual(len(r.notes), 1)
		self.assertIn("output VAT 18.00", r.notes[0])

	def test_entries_listed_under_the_most_specific_line(self):
		services = reverse_charge(EU_SERVICES, 10_000)
		private = purchase(PRIVATE, 2_000, output=360, rates=(18, 18))
		r = compute([services, private])
		self.assertEqual([e[0] for e in r.entries["3_ic"]], [services])
		self.assertEqual([e[0] for e in r.entries["3_nr18"]], [private])
		self.assertEqual([e[0] for e in r.entries["9a"]], [services])
		self.assertNotIn("3", r.entries)


class TestRounding(unittest.TestCase):
	"""Purchase VAT is the rate times the tax base of a line, unrounded until shown; sales VAT is as invoiced."""

	def test_purchase_vat_from_the_box_total(self):
		# Three invoices of 10.03 at 18%: 1.81 booked on each, 5.4162 on the total.
		r = compute([purchase(OVERHEADS, 1_003, input_vat=181) for _ in range(3)])
		self.assertEqual(r.tax("31"), 542)
		self.assertEqual(r.tax("33"), 542)
		self.assertEqual(r.tax("42"), -542)
		self.assertEqual(r.booked, -543)
		self.assertEqual([e[2] for e in r.entries["31"]], [181, 181, 181])

	def test_reverse_charge_from_the_box_total(self):
		r = compute([purchase(EU_SERVICES, 1_003, 181, 181, (18, 18)) for _ in range(3)])
		self.assertEqual(r.tax("3"), 542)
		self.assertEqual(r.tax("9a"), 542)
		self.assertEqual(r.tax("17"), 0)
		self.assertEqual(r.booked, 0)

	def test_totals_from_unrounded_lines(self):
		r = compute(
			[purchase(EU_SERVICES, 1_003, 181, 181, (18, 18)), purchase(NON_EU, 1_003, 181, 181, (18, 18))]
		)
		self.assertEqual((r.tax("3"), r.tax("4")), (181, 181))
		self.assertEqual(r.tax("5"), 361)
		self.assertEqual(r.tax("12"), 361)

	def test_box_17_from_unrounded_lines(self):
		r = compute(
			[purchase(PRIVATE, 1_003, 181, 0, (18, 18)), purchase(EU_SERVICES, 1_003, 181, 181, (18, 18))]
		)
		self.assertEqual(r.tax("5"), 361)
		self.assertEqual(r.tax("12"), 181)
		self.assertEqual(r.tax("17"), 181)
		self.assertEqual(r.tax("42"), 181)
		self.assertEqual(r.booked, 181)

	def test_sales_vat_as_invoiced(self):
		r = compute([sale(MALTA_18, 10_000, 1_803, 18)])
		self.assertEqual(r.tax("18"), 1_803)
		self.assertEqual(r.tax("42"), 1_803)
		self.assertEqual(r.booked, 1_803)

	def test_mixed_rates_counted_as_booked(self):
		r = compute([purchase(OVERHEADS, 10_000, input_vat=1_234, rates=(18, 5))])
		self.assertEqual(r.tax("31"), 1_234)
		self.assertEqual(len(r.notes), 1)
		self.assertIn("as booked", r.notes[0])

	def test_shown_rounds_half_away_from_zero(self):
		self.assertEqual(return_form.shown(Fraction(1, 2)), 1)
		self.assertEqual(return_form.shown(Fraction(-1, 2)), -1)
		self.assertEqual(return_form.shown(Fraction(149, 100)), 1)


class TestPeriods(unittest.TestCase):
	def test_quarters(self):
		self.assertEqual(return_form.period_dates(2030, "Jan-Mar"), (date(2030, 1, 1), date(2030, 3, 31)))
		self.assertEqual(return_form.period_dates(2028, "Jan-Mar")[1], date(2028, 3, 31))
		self.assertEqual(return_form.period_dates(2030, "Oct-Dec"), (date(2030, 10, 1), date(2030, 12, 31)))

	def test_other_dates(self):
		dates = (date(2030, 8, 1), date(2030, 12, 31))
		self.assertEqual(return_form.period_dates(2030, return_form.OTHER_DATES, *dates), dates)
		with self.assertRaises(ValueError):
			return_form.period_dates(2030, return_form.OTHER_DATES)
		with self.assertRaises(ValueError):
			return_form.period_dates(2030, return_form.OTHER_DATES, dates[1], dates[0])
		with self.assertRaises(ValueError):
			return_form.period_dates(2030, "Q5")

	def test_labels(self):
		self.assertEqual(return_form.period_label(date(2030, 7, 1), date(2030, 9, 30)), "Jul - Sep 2030")
		self.assertEqual(
			return_form.period_label(date(2030, 8, 1), date(2030, 12, 31)), "1 Aug 2030 - 31 Dec 2030"
		)


class TestSettlement(unittest.TestCase):
	def balance(self, s: return_form.Settlement) -> int:
		return sum(s.accounts.values()) + s.settlement + s.rounding

	def test_excess_credit_with_rounding(self):
		movements = {"input": 10_000, "input_reverse": 30_000, "output": 0, "output_reverse": -35_001}
		s = return_form.settlement(movements, -5_000)
		self.assertEqual(s.computed, -4_999)
		self.assertEqual(s.accounts, {"input": -10_000, "input_reverse": -30_000, "output_reverse": 35_001})
		self.assertEqual(s.settlement, 5_000)
		self.assertEqual(s.rounding, -1)
		self.assertEqual(self.balance(s), 0)

	def test_payable_without_rounding(self):
		s = return_form.settlement({"input": 2_000, "output": -5_000}, 3_000)
		self.assertEqual(s.settlement, -3_000)
		self.assertEqual(s.rounding, 0)
		self.assertEqual(self.balance(s), 0)

	def test_reverse_charge_only(self):
		s = return_form.settlement({"input_reverse": 5_000, "output_reverse": -5_000}, 0)
		self.assertEqual(s.settlement, 0)
		self.assertEqual(s.rounding, 0)
		self.assertEqual(self.balance(s), 0)

	def test_difference_above_rounding_is_refused(self):
		with self.assertRaises(ValueError):
			return_form.settlement({"input": 1_000}, -1_000 + return_form.MAX_ROUNDING + 1)
		s = return_form.settlement({"input": 1_000}, -1_000 + return_form.MAX_ROUNDING)
		self.assertEqual(s.rounding, return_form.MAX_ROUNDING)


if __name__ == "__main__":
	unittest.main()
