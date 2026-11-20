"""Tests of the rule register of the registrations under Articles 11 and 12, of the Article 11 declaration with its
limit tests, and of the notices and the annual declaration of Article 12 (docs/vat-articles-11-12.md). All figures
are invented. The modules under test import no Frappe, so the tests also run without a site.

Run: bench --site <test site> run-tests --module malta_compliance.tests.test_vat_articles_11_12
  or: python -m unittest malta_compliance.tests.test_vat_articles_11_12
"""

import unittest
from datetime import date

from malta_compliance.vat import article12, categories, declaration, rules
from malta_compliance.vat.categories import ARTICLE_11, ARTICLE_12, CATEGORIES, NO_RETURN_BOX
from malta_compliance.vat.declaration import Document

GOODS_SOLD = "VAT Art 11 Box 1 Sale of goods"
ASSET_SOLD = "VAT Art 11 Box 1 Sale of capital asset"
SERVICES_MALTA = "VAT Art 11 Box 2 Services in Malta"
SERVICES_EU = "VAT Art 11 Box 2 Services EU business customer liable"
SERVICES_OUTSIDE = "VAT Art 11 Box 2 Services outside Malta"
STOCK = "VAT Art 11 Box 3 Stock for re-sale"
STOCK_EU = "VAT Art 11 Box 3 Stock for re-sale from EU"
CAPITAL = "VAT Art 11 Box 4 Capital assets"
EU_GOODS = "VAT Art 11 EU goods"
A12_EU_SERVICES = "VAT Art 12 EU services 18%"
A12_NON_EU_SERVICES = "VAT Art 12 Non-EU services 18%"
A12_GOODS = "VAT Art 12 EU goods 18%"
A12_STOCK = "VAT Art 12 EU goods for re-sale 5%"
A12_CAPITAL = "VAT Art 12 EU capital goods 18%"

_numbers = iter(range(1, 10000))


def sale(category: str, on: str, amount: int) -> Document:
	return Document(
		"Sales Invoice", f"SINV-{next(_numbers):05d}", date.fromisoformat(on), "Customer", category, amount
	)


def purchase(category: str, on: str, amount: int, invoiced: str | None = None) -> Document:
	"""A purchase booked gross; with a category of Article 12, `amount` is the net total and the VAT is added."""
	charged = categories.ARTICLE_12_BY_TITLE.get(category)
	vat = amount * charged.rate // 100 if charged else 0
	return Document(
		"Purchase Invoice",
		f"PINV-{next(_numbers):05d}",
		date.fromisoformat(on),
		"Supplier",
		category,
		amount + vat,
		amount,
		vat,
		date.fromisoformat(invoiced) if invoiced else None,
	)


class TestCategories(unittest.TestCase):
	def test_titles_unique_across_the_registrations(self):
		titles = [c[0] for c in CATEGORIES] + [c.title for c in ARTICLE_11] + [c.title for c in ARTICLE_12]
		self.assertEqual(len(titles), len(set(titles)))

	def test_boxes_and_turnover(self):
		boxes = {box for box, _label in categories.ARTICLE_11_BOXES}
		for category in ARTICLE_11:
			self.assertIn(category.direction, (categories.SALES, categories.PURCHASE), category.title)
			self.assertTrue(category.box is None or category.box in boxes, category.title)
			if category.direction == categories.SALES:
				self.assertIn(category.box, ("1", "2"), category.title)
				self.assertFalse(category.eu_goods, category.title)
			else:
				self.assertIsNone(category.turnover, category.title)
				self.assertIn(category.box, ("3", "4", None), category.title)
		self.assertIsNone(categories.ARTICLE_11_BY_TITLE[ASSET_SOLD].turnover)
		self.assertTrue(categories.ARTICLE_11_BY_TITLE[SERVICES_EU].eu_customer)

	def test_article_12_templates_charge_without_deduction(self):
		for category in ARTICLE_12:
			self.assertIn(category.kind, (categories.SERVICES, categories.GOODS), category.title)
			self.assertIn(f"{category.rate}%", category.title)
			self.assertEqual(
				category.rows,
				((categories.COST, category.rate, "Add"), ("output_reverse", category.rate, "Deduct")),
			)
			if category.kind == categories.SERVICES:
				self.assertIsNone(category.box, category.title)
			else:
				self.assertTrue(category.eu, category.title)


class TestRules(unittest.TestCase):
	def test_versions_cover_every_day_from_1999(self):
		versions = rules.SMALL_ENTERPRISES
		self.assertEqual(versions[0].first, date(1999, 1, 1))
		self.assertIsNone(versions[-1].last)
		for earlier, later in zip(versions, versions[1:], strict=False):
			self.assertEqual((later.first - earlier.last).days, 1)
		with self.assertRaises(rules.NotCovered):
			rules.small_enterprise(date(1998, 12, 31))

	def test_limits_by_date_and_activity(self):
		def limit(on: str, activity: str) -> int:
			return rules.small_enterprise(date.fromisoformat(on)).stay_limit(activity)

		self.assertEqual(limit("2010-06-30", rules.GOODS), 3_500_000)
		self.assertEqual(limit("2010-06-30", rules.LOW_VALUE_SERVICES), 2_400_000)
		self.assertEqual(limit("2018-06-30", rules.OTHER), 1_400_000)
		self.assertEqual(limit("2018-07-01", rules.OTHER), 2_000_000)
		self.assertEqual(limit("2021-03-31", rules.OTHER), 1_400_000)
		self.assertEqual(limit("2021-07-01", rules.OTHER), 3_000_000)
		self.assertEqual(limit("2021-07-01", rules.LOW_VALUE_SERVICES), 3_000_000)
		self.assertEqual(limit("2024-12-31", rules.GOODS), 3_500_000)
		self.assertEqual(limit("2025-01-01", rules.OTHER), 3_500_000)

	def test_liri_at_the_irrevocable_rate(self):
		first = rules.small_enterprise(date(2000, 1, 1))
		self.assertEqual(first.currency, rules.MTL)
		self.assertEqual(first.entry, (12000, 8000, 5000))
		self.assertEqual(first.stay, (15000, 10000, 6000))
		self.assertEqual(first.stay_limit(rules.GOODS), 3_494_060)
		later = rules.small_enterprise(date(2005, 1, 1))
		self.assertEqual((later.entry, later.stay), ((15000, 10000, 6000), (12000, 8000, 5000)))
		fixed = rules.small_enterprise(date(2007, 4, 27))
		self.assertEqual(fixed.stay, fixed.entry)

	def test_period_and_place_of_supply(self):
		old, new = rules.small_enterprise(date(2024, 12, 31)), rules.small_enterprise(date(2025, 1, 1))
		self.assertEqual((old.period, old.domestic), (rules.RELEVANT_PERIOD, False))
		self.assertEqual((new.period, new.domestic), (rules.CALENDAR_YEAR, True))
		self.assertTrue(old.entry_below)
		self.assertFalse(new.entry_below)

	def test_exceeds(self):
		self.assertFalse(rules.exceeds(3_500_000, 3_500_000, below=False))
		self.assertTrue(rules.exceeds(3_500_001, 3_500_000, below=False))
		self.assertTrue(rules.exceeds(3_500_000, 3_500_000, below=True))

	def test_due_date_interest_and_penalty(self):
		self.assertEqual(rules.declaration_due(2025), date(2026, 3, 15))
		self.assertEqual(str(rules.interest(date(2013, 12, 31)).percent), "1")
		self.assertEqual(str(rules.interest(date(2019, 12, 31)).percent), "0.54")
		self.assertEqual(str(rules.interest(date(2022, 8, 31)).percent), "0.33")
		self.assertEqual(str(rules.interest(date(2022, 9, 1)).percent), "0.6")
		early, late = rules.late_declaration(date(2023, 4, 3)), rules.late_declaration(date(2023, 4, 4))
		self.assertEqual((early.per_month, early.maximum), (23, 580))
		self.assertEqual((late.per_month, late.maximum), (10, 120))
		with self.assertRaises(rules.NotCovered):
			rules.late_declaration(date(2007, 12, 31))

	def test_review_warning(self):
		self.assertIsNone(rules.review_warning(rules.REVIEWED_UP_TO))
		self.assertIn(str(rules.REVIEWED_UP_TO), rules.review_warning(rules.REVIEWED_UP_TO + 1))


class TestDeclaration(unittest.TestCase):
	def test_boxes(self):
		documents = [
			sale(GOODS_SOLD, "2030-02-01", 120_000),
			sale(ASSET_SOLD, "2030-03-01", 30_000),
			sale(SERVICES_MALTA, "2030-04-01", 500_000),
			sale(SERVICES_EU, "2030-05-01", 200_000),
			sale(SERVICES_OUTSIDE, "2030-06-01", 90_000),
			sale(SERVICES_MALTA, "2030-07-01", -10_000),
			purchase(STOCK, "2030-02-10", 40_000),
			purchase(STOCK_EU, "2030-02-11", 12_100),
			purchase(CAPITAL, "2030-03-10", 99_900),
			purchase(EU_GOODS, "2030-03-11", 5_000),
			purchase(NO_RETURN_BOX, "2030-03-12", 7_000),
		]
		result = declaration.declaration(documents)
		self.assertEqual(result.boxes, {"1": 150_000, "2": 780_000, "3": 52_100, "4": 99_900})
		self.assertEqual([d.category for d in result.outside], [EU_GOODS, NO_RETURN_BOX])
		self.assertEqual(result.unknown, [])
		self.assertEqual(len(result.entries["2"]), 4)

	def test_purchases_under_article_12_enter_at_cost(self):
		documents = [
			purchase(A12_STOCK, "2030-02-10", 10_000),
			purchase(A12_CAPITAL, "2030-02-11", 100_000),
			purchase(A12_EU_SERVICES, "2030-02-12", 50_000),
		]
		result = declaration.declaration(documents)
		self.assertEqual(result.boxes["3"], 10_500)
		self.assertEqual(result.boxes["4"], 118_000)
		self.assertEqual([d.category for d in result.outside], [A12_EU_SERVICES])

	def test_categories_of_other_registrations_are_unknown(self):
		documents = [
			sale("VAT Box 1 EU business customer liable", "2030-02-01", 1_000),
			sale("", "2030-02-02", 2_000),
			sale(STOCK, "2030-02-03", 3_000),
			purchase(GOODS_SOLD, "2030-02-04", 4_000),
			sale(NO_RETURN_BOX, "2030-02-05", 5_000),
		]
		result = declaration.declaration(documents)
		self.assertEqual(len(result.unknown), 5)
		self.assertEqual(sum(result.boxes.values()), 0)


class TestTurnoverLimit(unittest.TestCase):
	def test_relevant_period(self):
		self.assertEqual(
			declaration.relevant_period(date(2024, 5, 10)), (date(2023, 4, 1), date(2024, 3, 31), 4)
		)
		self.assertEqual(
			declaration.relevant_period(date(2024, 1, 1)), (date(2023, 1, 1), date(2023, 12, 31), 4)
		)
		self.assertEqual(
			declaration.relevant_period(date(2024, 5, 10), started=date(2023, 8, 20)),
			(date(2023, 10, 1), date(2024, 3, 31), 2),
		)
		self.assertIsNone(declaration.relevant_period(date(2023, 11, 10), started=date(2023, 8, 20)))

	def test_supplies_outside_malta_count_until_2024(self):
		documents = [
			sale(SERVICES_MALTA, "2024-03-01", 1_000_000),
			sale(SERVICES_EU, "2024-03-02", 1_500_000),
			sale(ASSET_SOLD, "2024-03-03", 900_000),
			sale(SERVICES_MALTA, "2025-03-01", 1_000_000),
			sale(SERVICES_EU, "2025-03-02", 1_500_000),
			sale(SERVICES_OUTSIDE, "2025-03-03", 700_000),
		]
		old, new = rules.small_enterprise(date(2024, 12, 31)), rules.small_enterprise(date(2025, 1, 1))
		year = (date(2024, 1, 1), date(2024, 12, 31))
		self.assertEqual(declaration.turnover(documents, *year, old), 2_500_000)
		self.assertEqual(declaration.turnover(documents, *year, new), 1_000_000)
		year = (date(2025, 1, 1), date(2025, 12, 31))
		self.assertEqual(declaration.turnover(documents, *year, new), 1_000_000)

	def test_quarterly_tests_until_2024(self):
		documents = [
			sale(SERVICES_MALTA, "2023-02-01", 1_200_000),
			sale(SERVICES_MALTA, "2023-08-01", 1_000_000),
			sale(SERVICES_EU, "2024-02-01", 900_000),
			sale(SERVICES_MALTA, "2024-05-01", 500_000),
		]
		tests = declaration.limit_tests(documents, 2024, rules.OTHER)
		self.assertEqual(
			[t.label for t in tests],
			[
				"12 months to 31 Dec 2023",
				"12 months to 31 Mar 2024",
				"12 months to 30 Jun 2024",
				"12 months to 30 Sep 2024",
			],
		)
		self.assertEqual([t.value for t in tests], [2_200_000, 1_900_000, 2_400_000, 1_400_000])
		self.assertEqual({t.limit for t in tests}, {3_000_000})
		self.assertFalse(any(t.exceeded for t in tests))
		goods = declaration.limit_tests(documents, 2024, rules.GOODS)
		self.assertEqual({t.limit for t in goods}, {3_500_000})

	def test_limit_exceeded_until_2024(self):
		documents = [sale(SERVICES_MALTA, "2019-11-01", 2_000_000), sale(SERVICES_MALTA, "2020-02-01", 1)]
		tests = declaration.limit_tests(documents, 2020, rules.OTHER)
		self.assertEqual([t.exceeded for t in tests], [False, True, True, True])
		self.assertEqual(tests[1].value, 2_000_001)

	def test_new_activity_is_tested_in_proportion(self):
		documents = [sale(SERVICES_MALTA, "2023-11-01", 1_600_000)]
		tests = declaration.limit_tests(documents, 2024, rules.OTHER, started=date(2023, 8, 20))
		self.assertEqual([t.label for t in tests][:2], ["3 months to 31 Dec 2023", "6 months to 31 Mar 2024"])
		self.assertEqual([t.limit for t in tests], [750_000, 1_500_000, 2_250_000, 3_000_000])
		self.assertEqual([t.exceeded for t in tests], [True, True, False, False])

	def test_calendar_year_from_2025(self):
		documents = [
			sale(SERVICES_MALTA, "2024-06-01", 3_400_000),
			sale(SERVICES_EU, "2024-07-01", 5_000_000),
			sale(SERVICES_MALTA, "2025-02-01", 2_000_000),
			sale(SERVICES_EU, "2025-03-01", 9_000_000),
			sale(SERVICES_MALTA, "2025-08-12", 1_500_000),
			sale(SERVICES_MALTA, "2025-09-01", 100_000),
			sale(SERVICES_MALTA, "2025-12-01", -200_000),
		]
		current, preceding = declaration.limit_tests(documents, 2025, rules.OTHER)
		self.assertEqual(current.label, "Calendar year 2025")
		self.assertEqual((current.value, current.limit), (3_400_000, 3_500_000))
		self.assertFalse(current.preceding)
		self.assertTrue(current.exceeded)
		self.assertEqual(current.exceeded_on, date(2025, 9, 1))
		self.assertTrue(preceding.preceding)
		self.assertEqual((preceding.value, preceding.exceeded), (3_400_000, False))

	def test_limit_reached_but_not_exceeded(self):
		documents = [sale(SERVICES_MALTA, "2026-02-01", 3_500_000)]
		current, _preceding = declaration.limit_tests(documents, 2026, rules.OTHER)
		self.assertFalse(current.exceeded)
		self.assertIsNone(current.exceeded_on)

	def test_year_before_the_register(self):
		with self.assertRaises(rules.NotCovered):
			declaration.limit_tests([], 1998, rules.OTHER)


class TestAcquisitions(unittest.TestCase):
	def test_threshold(self):
		documents = [
			purchase(STOCK_EU, "2030-02-01", 600_000),
			purchase(A12_GOODS, "2030-03-01", 300_000),
			purchase(EU_GOODS, "2030-04-01", 100_000),
			purchase(STOCK, "2030-04-02", 900_000),
			purchase(A12_EU_SERVICES, "2030-04-03", 900_000),
			purchase(EU_GOODS, "2030-05-01", 1),
		]
		test = declaration.acquisitions(documents, 2030)
		self.assertEqual(test.value, 1_000_001)
		self.assertEqual(test.limit, 1_000_000)
		self.assertTrue(test.exceeded)
		self.assertEqual(test.exceeded_on, date(2030, 5, 1))

	def test_before_the_accession(self):
		self.assertIsNone(declaration.acquisitions([], 2003))
		documents = [purchase(EU_GOODS, "2004-03-01", 2_000_000), purchase(EU_GOODS, "2004-06-01", 5_000)]
		test = declaration.acquisitions(documents, 2004)
		self.assertEqual((test.first, test.value, test.exceeded), (date(2004, 5, 1), 5_000, False))

	def test_services_to_eu_customers_from_2025(self):
		documents = [sale(SERVICES_EU, "2024-12-31", 1_000), sale(SERVICES_EU, "2025-01-01", 2_000)]
		self.assertEqual(declaration.eu_customer_services(documents, 2024), [])
		self.assertEqual([d.amount for d in declaration.eu_customer_services(documents, 2025)], [2_000])


class TestArticle12(unittest.TestCase):
	def test_due_dates(self):
		day = date.fromisoformat
		self.assertEqual(article12.goods_due(day("2030-03-10"), day("2030-03-10")), day("2030-04-15"))
		self.assertEqual(article12.goods_due(day("2030-03-28"), day("2030-04-20")), day("2030-05-15"))
		self.assertEqual(article12.goods_due(day("2030-12-05"), day("2030-12-05")), day("2031-01-15"))
		self.assertEqual(article12.services_due(day("2030-03-10"), day("2030-03-10")), day("2030-05-15"))
		self.assertEqual(article12.services_due(day("2030-12-20"), day("2031-01-05")), day("2031-02-15"))
		self.assertEqual(article12.services_due(day("2030-04-02"), day("2030-03-30")), day("2030-05-15"))

	def test_notices(self):
		documents = [
			purchase(A12_EU_SERVICES, "2030-03-10", 10_000),
			purchase(A12_GOODS, "2030-03-11", 20_000),
			purchase(A12_NON_EU_SERVICES, "2030-02-01", 5_000, invoiced="2030-01-31"),
			purchase(STOCK, "2030-03-12", 1_000),
		]
		found = article12.notices(documents)
		self.assertEqual([n.due for n in found], [date(2030, 3, 15), date(2030, 4, 15), date(2030, 5, 15)])
		self.assertEqual(
			[(n.kind, n.eu) for n in found], [("Services", False), ("Goods", True), ("Services", True)]
		)
		self.assertEqual([(n.value, n.vat) for n in found], [(5_000, 900), (20_000, 3_600), (10_000, 1_800)])

	def test_purchase_before_article_12_covered_it(self):
		with self.assertRaises(rules.NotCovered):
			article12.notices([purchase(A12_EU_SERVICES, "2009-12-31", 1_000)])
		with self.assertRaises(rules.NotCovered):
			article12.notices([purchase(A12_GOODS, "2004-04-30", 1_000)])
		self.assertEqual(len(article12.notices([purchase(A12_GOODS, "2004-05-01", 1_000)])), 1)

	def test_payments_applied_in_the_order_of_the_due_dates(self):
		found = article12.notices(
			[
				purchase(A12_EU_SERVICES, "2030-01-10", 10_000),
				purchase(A12_EU_SERVICES, "2030-02-10", 20_000),
				purchase(A12_EU_SERVICES, "2030-03-10", 30_000),
			]
		)
		settled, excess = article12.settle(found, [(date(2030, 3, 14), 1_800), (date(2030, 4, 20), 2_000)])
		self.assertEqual([s.paid for s in settled], [1_800, 2_000, 0])
		self.assertEqual([s.open for s in settled], [0, 1_600, 5_400])
		self.assertEqual([s.paid_on for s in settled], [date(2030, 3, 14), date(2030, 4, 20), None])
		self.assertEqual(excess, 0)
		_settled, excess = article12.settle(found, [(date(2030, 6, 1), 11_000)])
		self.assertEqual(excess, 200)

	def test_credit_note_counts_as_a_payment(self):
		found = article12.notices(
			[purchase(A12_EU_SERVICES, "2030-01-10", 10_000), purchase(A12_EU_SERVICES, "2030-01-20", -4_000)]
		)
		settled, excess = article12.settle(found, [])
		by_vat = {s.notice.vat: s for s in settled}
		self.assertEqual((by_vat[1_800].paid, by_vat[1_800].open), (720, 1_080))
		self.assertEqual((by_vat[-720].paid, by_vat[-720].open), (0, 0))
		self.assertEqual(excess, 0)

	def test_annual_declaration(self):
		found = article12.notices(
			[
				purchase(A12_EU_SERVICES, "2030-03-10", 10_000),
				purchase("VAT Art 12 EU services 5%", "2030-04-10", 2_000),
				purchase(A12_NON_EU_SERVICES, "2030-05-10", 5_000),
				purchase(A12_GOODS, "2030-06-10", 20_000),
				purchase(A12_STOCK, "2030-07-10", 4_000),
				purchase(A12_EU_SERVICES, "2031-01-05", 99_000),
				purchase(A12_EU_SERVICES, "2030-12-28", 1_000, invoiced="2031-01-03"),
			]
		)
		lines = article12.annual(found, 2030)
		self.assertEqual(lines[article12.EU_SERVICES], [13_000, 2_080])
		self.assertEqual(lines[article12.NON_EU_SERVICES], [5_000, 900])
		self.assertEqual(lines[article12.ACQUISITIONS], [24_000, 3_800])
		self.assertEqual(article12.annual(found, 2031)[article12.EU_SERVICES], [99_000, 17_820])


if __name__ == "__main__":
	unittest.main()
