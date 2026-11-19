"""Integration tests of the record Malta Taxpayer, the years built from it and the report "Tax Payments Malta" on a
test site (docs/income-tax.md). One company with income, expenses and payments booked by Journal Entries; the
taxpayer has filed returns for 2023 and 2024 and none for 2025. All figures are invented.

Run: bench --site <test site> run-tests --module malta_compliance.tests.test_taxpayer
"""

import unittest

import frappe

from malta_compliance.malta_compliance.doctype.malta_tax_year import malta_tax_year
from malta_compliance.malta_compliance.report.tax_payments_malta import tax_payments_malta
from malta_compliance.tax import taxpayer as taxpayer_record
from malta_compliance.tax import year as tax_year
from malta_compliance.tests.test_tax_year import journal, make_company

TAXPAYER = "MC Test Payer"


def payments_report(company: str, year: int, as_of: str) -> tuple[list[dict], str]:
	result = tax_payments_malta.execute({"company": company, "year": year, "as_of": as_of})
	return result[1], result[2]


class TestMaltaTaxpayer(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.own = make_company("MTE")
		for doctype in ("Malta Tax Year", "Malta Taxpayer"):
			for name in frappe.get_all(doctype, filters={"name": ["like", f"{TAXPAYER}%"]}, pluck="name"):
				frappe.delete_doc(doctype, name, force=True)
		journal("payer income", cls.own, "2025-03-31", "3200", "4100", 60000)
		journal("payer expense", cls.own, "2025-06-30", "5200", "3200", 10000)
		journal("payer pt 1", cls.own, "2025-04-20", "3210", "3200", 600)
		journal("payer class 2", cls.own, "2025-04-22", "3220", "3200", 1152.43)
		journal("payer settlement", cls.own, "2025-06-25", "3210", "3200", 4000)
		journal("payer pt 2", cls.own, "2025-08-20", "3210", "3200", 900)
		cls.master = frappe.get_doc(
			{
				"doctype": "Malta Taxpayer",
				"taxpayer_name": TAXPAYER,
				"status": "Married",
				"self_year_of_birth": 1958,
				"self_occupied_from": "2022-03-01",
				"spouse_name": "MC Test Spouse",
				"companies": [{"company": cls.own, "person": "Self"}],
				"returns": [
					{
						"basis_year": "2023",
						"self_net_profit": 20000,
						"chargeable_income": 20000,
						"tax_charged": 3000,
					},
					{
						"basis_year": "2024",
						"self_net_profit": 35000,
						"spouse_net_profit": 16000,
						"chargeable_income": 51000,
						"tax_charged": 6000,
						"provisional_tax_paid": 1000,
					},
				],
			}
		).insert()

	def setUp(self):
		frappe.set_user("Administrator")
		taxpayer_record.clear_cache()

	def test_1_built_years(self):
		self.assertEqual(taxpayer_record.for_company(self.own), TAXPAYER)
		self.assertEqual(taxpayer_record.first_year(self.master), 2022)
		self.assertIsNone(taxpayer_record.built_year(TAXPAYER, 2021))
		filed = tax_year.find(TAXPAYER, 2024)
		self.assertTrue(filed.is_new())
		self.assertEqual((filed.filed, filed.filed_tax, len(filed.companies)), (1, 6000, 0))
		self.assertEqual(tax_year.net_earnings(filed, "Spouse"), 16000)
		self.assertEqual(tax_year.payment_total(filed, tax_year.PROVISIONAL_TAX), 1000)
		built = tax_year.find(TAXPAYER, 2025)
		self.assertEqual(([row.company for row in built.companies], built.filed), ([self.own], 0))
		self.assertEqual((built.self_class2_base_entered, built.self_class2_base), (1, 35000))
		self.assertEqual((built.spouse_class2_base_entered, built.spouse_class2_base), (1, 16000))
		self.assertEqual(
			{p.amount: p.kind for p in built.payments},
			{
				600: tax_year.PROVISIONAL_TAX,
				1152.43: tax_year.CLASS2,
				4000: tax_year.SETTLEMENT_PRECEDING,
				900: tax_year.PROVISIONAL_TAX,
			},
		)

	def test_2_payments_of_a_year_with_the_preceding_return_filed(self):
		rows, message = payments_report(self.own, 2025, "2025-09-15")
		self.assertEqual(len(rows), 11)
		self.assertEqual([str(r["due"]) for r in rows[:2]], ["2025-04-30", "2025-04-30"])
		settlement = next(r for r in rows if r["payment"] == "Income tax 2024, balance")
		self.assertEqual(
			(str(settlement["due"]), settlement["amount"], settlement["paid"], settlement["open"]),
			("2025-06-30", 5000, 4000, 1000),
		)
		provisional = [r for r in rows if r["payment"].startswith("Provisional tax")]
		self.assertEqual([(r["amount"], r["paid"]) for r in provisional], [(600, 600), (900, 900), (1500, 0)])
		own = [r for r in rows if r["payment"].startswith("Class 2") and r["person"] == "Self"]
		self.assertEqual([r["amount"] for r in own], [1152.43, 1152.43, 1220.22])
		self.assertEqual([r["paid"] for r in own], [1152.43, 0, 0])
		spouse = [r for r in rows if r["person"] == "Spouse"]
		self.assertEqual([r["amount"] for r in spouse], [784.55, 784.55, 830.7])
		self.assertEqual(rows[-1]["payment"], "Total")
		self.assertAlmostEqual(rows[-1]["amount"], 13924.88, places=2)
		self.assertIn("Built from the Malta Taxpayer", message)
		self.assertIn("Benchmark 3000", message)

	def test_3_class_2_base_from_the_books(self):
		rows, _message = payments_report(self.own, 2026, "2026-01-01")
		own = [r for r in rows if r["payment"].startswith("Class 2")]
		self.assertEqual([r["amount"] for r in own], [1250.52, 1324.08, 1250.52])
		self.assertEqual({r["person"] for r in own}, {"Self"})
		provisional = [r for r in rows if r["payment"].startswith("Provisional tax")]
		self.assertEqual([r["amount"] for r in provisional], [1200, 1800, 3000])
		settlement = next(r for r in rows if r["payment"].startswith("Income tax 2025"))
		expected = tax_year.tax_payable(tax_year.find(TAXPAYER, 2025)) - 1500
		self.assertEqual((settlement["amount"], settlement["paid"]), (expected, 0))

	def test_4_saved_year_takes_precedence(self):
		doc = frappe.get_doc(
			{
				"doctype": "Malta Tax Year",
				"taxpayer": TAXPAYER,
				"basis_year": "2026",
				"status": "Married",
				"self_class2_base_entered": 1,
				"self_class2_base": 20000,
			}
		).insert()
		try:
			rows, message = payments_report(self.own, 2026, "2026-01-01")
			own = [r for r in rows if r["payment"].startswith("Class 2")]
			self.assertEqual(own[0]["amount"], 980.73)
			self.assertIn(f"saved Malta Tax Year {doc.name}", message)
		finally:
			frappe.delete_doc("Malta Tax Year", doc.name, force=True)

	def test_5_new_year_record_filled_from_the_taxpayer(self):
		values = malta_tax_year.taxpayer_defaults(TAXPAYER, "2025")
		self.assertEqual((values["status"], values["self_born_before_1962"]), ("Married", 1))
		self.assertEqual(values["companies"], [{"company": self.own, "person": "Self"}])
		self.assertEqual((values["self_class2_base_entered"], values["self_class2_base"]), (1, 35000))
		filed = malta_tax_year.taxpayer_defaults(TAXPAYER, "2024")
		self.assertEqual((filed["filed"], filed["filed_tax"], filed["companies"]), (1, 6000, []))
		self.assertEqual(
			[(i["person"], i["amount"]) for i in filed["items"]], [("Self", 35000), ("Spouse", 16000)]
		)
		self.assertEqual(malta_tax_year.taxpayer_defaults(TAXPAYER, "20x5"), {})

	def test_6_validation(self):
		twice = frappe.get_doc(
			{
				"doctype": "Malta Taxpayer",
				"taxpayer_name": "MC Test Payer Two",
				"companies": [{"company": self.own, "person": "Self"}],
			}
		)
		self.assertRaises(frappe.ValidationError, twice.insert)
		master = frappe.get_doc("Malta Taxpayer", TAXPAYER)
		master.append("returns", {"basis_year": "2023", "tax_charged": 1})
		self.assertRaises(frappe.ValidationError, master.save)
		with self.assertRaises(frappe.ValidationError):
			payments_report(make_company("MTF"), 2025, "2025-01-01")
