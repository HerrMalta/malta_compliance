"""Integration tests of the record Malta Tax Year and its three reports on a test site (docs/income-tax.md). The
class sets up two companies with setup_company and books their income, expenses and payments with Journal Entries.
All figures are invented.

Run: bench --site <test site> run-tests --module malta_compliance.tests.test_tax_year
"""

import unittest

import frappe

from malta_compliance.malta_compliance.report.income_tax_computation_malta import income_tax_computation_malta
from malta_compliance.malta_compliance.report.provisional_tax_malta import provisional_tax_malta
from malta_compliance.malta_compliance.report.social_security_contributions_malta import (
	social_security_contributions_malta,
)
from malta_compliance.setup.company import setup_company
from malta_compliance.setup.vat import account
from malta_compliance.tax import books
from malta_compliance.tax import year as tax_year

TAXPAYER = "MC Test Taxpayer"


def make_company(abbr: str) -> str:
	frappe.set_user("Administrator")
	result = setup_company(
		company_name=f"MC Test {abbr}", abbr=abbr, vat_article=10, fiscal_years=list(range(2020, 2032))
	)
	return result["company"]


def journal(company: str, date: str, debit: str, credit: str, amount: float) -> str:
	"""Journal Entry between two accounts given by number; returns its name."""
	cost_center = frappe.get_cached_value("Company", company, "cost_center")
	doc = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"company": company,
			"posting_date": date,
			"accounts": [
				{
					"account": account(company, debit),
					"debit_in_account_currency": amount,
					"cost_center": cost_center,
				},
				{
					"account": account(company, credit),
					"credit_in_account_currency": amount,
					"cost_center": cost_center,
				},
			],
		}
	)
	doc.insert()
	doc.submit()
	return doc.name


def make_year(basis_year: int, **fields):
	doc = frappe.get_doc(
		{"doctype": "Malta Tax Year", "taxpayer": TAXPAYER, "basis_year": str(basis_year), **fields}
	)
	doc.insert()
	return doc


def report_rows(module, name: str, **filters) -> tuple[list[dict], str]:
	result = module.execute({"malta_tax_year": name, **filters})
	return result[1], result[2]


def by(rows: list[dict], key: str, value: str) -> dict:
	return next(row for row in rows if row.get(key) == value)


class TestMaltaTaxYear(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.own = make_company("MTA")
		cls.spouse = make_company("MTB")
		for name in frappe.get_all("Malta Tax Year", filters={"taxpayer": TAXPAYER}, pluck="name"):
			frappe.delete_doc("Malta Tax Year", name, force=True)
		if not books.profit(cls.own, 2025):
			journal(cls.own, "2025-03-31", "3200", "4100", 60000)
			journal(cls.own, "2025-06-30", "5200", "3200", 10000)
			journal(cls.spouse, "2025-05-31", "3200", "4300", 8000)
			journal(cls.own, "2025-04-25", "3210", "3200", 340)
			journal(cls.own, "2025-09-10", "3210", "3200", 510)
			journal(cls.own, "2025-04-28", "3220", "3200", 735.59)
		make_year(
			2023,
			status="Married",
			filed=1,
			filed_tax=2000,
			items=[{"kind": tax_year.TAX_AT_SOURCE, "person": "Self", "amount": 300}],
		)
		make_year(
			2024,
			status="Married",
			items=[{"kind": tax_year.TRADE, "person": "Self", "description": "Trade", "amount": 15000.80}],
		)
		cls.year = make_year(
			2025,
			status="Married",
			spouse_first_year=1,
			companies=[
				{"company": cls.own, "person": "Self"},
				{"company": cls.spouse, "person": "Spouse"},
			],
		)

	def setUp(self):
		frappe.set_user("Administrator")

	def test_1_profit_and_payments_from_the_books(self):
		self.assertEqual(books.profit(self.own, 2025), 50000)
		self.assertEqual(books.profit(self.spouse, 2025), 8000)
		self.assertEqual(self.year.year_of_assessment, "2026")
		self.assertEqual(self.year.fetch_payments(), 3)
		self.assertEqual(self.year.fetch_payments(), 0)
		kinds = {(str(p.posting_date), p.kind or "", p.person) for p in self.year.payments}
		self.assertEqual(
			kinds,
			{("2025-04-25", "", "Self"), ("2025-09-10", "", "Self"), ("2025-04-28", tax_year.CLASS2, "Self")},
		)
		for payment in self.year.payments:
			if not payment.kind:
				payment.kind = tax_year.PROVISIONAL_TAX
		self.year.save()

	def test_2_income_tax_computation(self):
		rows, message = report_rows(income_tax_computation_malta, self.year.name)
		separate = by(rows, "line", "Separate computation: tax (box 26)")
		self.assertEqual((separate["own"], separate["spouse"], separate["total"]), (9100, 0, 9100))
		self.assertEqual(by(rows, "line", "Joint computation: tax (box 26)")["total"], 9950)
		charged = by(rows, "line", "Tax charged (box 27)")
		self.assertEqual((charged["total"], charged["note"]), (9100, "Separate computation"))
		self.assertEqual(by(rows, "line", "Provisional tax paid (box 36)")["total"], -850)
		self.assertEqual(by(rows, "line", "Tax underpaid (+) or overpaid (-) (box 42)")["total"], 8250)
		self.assertIn("Act IX of 2025", message)

	def test_3_provisional_tax(self):
		rows, message = report_rows(provisional_tax_malta, self.year.name, as_of="2026-08-15")
		self.assertEqual([r["amount"] for r in rows], [340, 510, 850, 1700])
		self.assertEqual([r["paid"] for r in rows], [340, 510, 0, 850])
		self.assertEqual([r["additional_tax"] for r in rows], [0, 3.06, 30.6, 33.66])
		self.assertEqual(rows[2]["open"], 850)
		self.assertIn("Benchmark 1700", message)

	def test_4_class_2_contributions(self):
		rows, message = report_rows(social_security_contributions_malta, self.year.name, as_of="2025-10-15")
		own = [r for r in rows if r["person"] == "Self"]
		self.assertEqual([r["weeks"] for r in own], [17, 17, 18, 52])
		self.assertEqual((own[0]["category"], own[0]["weekly_rate"]), ("SB", 43.27))
		self.assertEqual([r["amount"] for r in own], [735.59, 735.59, 778.86, 2250.04])
		self.assertEqual([r["paid"] for r in own], [735.59, 0, 0, 735.59])
		self.assertEqual([r["addition"] for r in own], [0, 14.71, 0, 14.71])
		spouse = [r for r in rows if r["person"] == "Spouse"]
		self.assertEqual((spouse[0]["category"], spouse[0]["weekly_rate"]), ("SA", 35.48))
		self.assertEqual(spouse[3]["amount"], 1844.96)
		self.assertIn("15000", message)

	def test_5_validation(self):
		with self.assertRaises(frappe.ValidationError):
			make_year(
				2026, status="Single", items=[{"kind": tax_year.TRADE, "person": "Spouse", "amount": 1}]
			)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Malta Tax Year", "taxpayer": TAXPAYER, "basis_year": "20x7"}).insert()
		with self.assertRaises(frappe.ValidationError):
			make_year(2027, companies=[{"company": self.own}, {"company": self.own}])
