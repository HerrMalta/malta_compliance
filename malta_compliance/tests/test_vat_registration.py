"""Integration tests of the record Malta VAT Registration and of the reports "VAT Declaration Article 11 Malta" and
"VAT Article 12 Malta" on a test site (docs/vat-articles-11-12.md). One company registered under Article 11 with a
registration under Article 12 beside it; its invoices and one payment of self-charged VAT are booked once per site,
each carrying a tag in its remark. All figures are invented.

Run: bench --site <test site> run-tests --module malta_compliance.tests.test_vat_registration
"""

import unittest

import frappe

from malta_compliance.malta_compliance.report.vat_article_12_malta import vat_article_12_malta
from malta_compliance.malta_compliance.report.vat_declaration_article_11_malta import (
	vat_declaration_article_11_malta,
)
from malta_compliance.patches.v0_5 import vat_registrations
from malta_compliance.setup.company import SERVICE_ITEM, setup_company
from malta_compliance.setup.vat import account
from malta_compliance.tests.test_capital_allowances import balance
from malta_compliance.tests.test_tax_year import journal
from malta_compliance.vat import registration
from malta_compliance.vat.categories import ARTICLE_11, ARTICLE_12

CUSTOMER = "MC Test Customer"
SUPPLIER = "MC Test Supplier"
YEARS = list(range(2020, 2032))
SERVICES_MALTA = "VAT Art 11 Box 2 Services in Malta"
SERVICES_EU = "VAT Art 11 Box 2 Services EU business customer liable"
STOCK = "VAT Art 11 Box 3 Stock for re-sale"
CAPITAL = "VAT Art 11 Box 4 Capital assets"
NO_BOX = "VAT No return box"
A12_EU_SERVICES = "VAT Art 12 EU services 18%"
A12_NON_EU_SERVICES = "VAT Art 12 Non-EU services 18%"
A12_STOCK = "VAT Art 12 EU goods for re-sale 5%"
TEMPLATE = "Purchase Taxes and Charges Template"
TAX_FIELDS = ("category", "add_deduct_tax", "charge_type", "account_head", "rate", "description", "cost_center")


def ensure_party(doctype: str, name: str) -> None:
	if frappe.db.exists(doctype, name):
		return
	field = "customer" if doctype == "Customer" else "supplier"
	frappe.get_doc({"doctype": doctype, f"{field}_name": name, f"{field}_type": "Company"}).insert()


def sale(tag: str, company: str, date: str, category: str, amount: float, income: str) -> None:
	"""Submitted Sales Invoice without VAT rows, unless an invoice with the tag exists."""
	remark = f"MC vat test {tag}"
	if frappe.db.exists("Sales Invoice", {"remarks": remark, "docstatus": 1}):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": company,
			"customer": CUSTOMER,
			"posting_date": date,
			"set_posting_time": 1,
			"due_date": date,
			"tax_category": category,
			"remarks": remark,
			"items": [
				{"item_code": SERVICE_ITEM, "qty": 1, "rate": amount, "income_account": account(company, income)}
			],
		}
	)
	doc.insert()
	doc.submit()


def purchase(
	tag: str, company: str, date: str, category: str, amount: float, invoiced: str | None = None
) -> None:
	"""Submitted Purchase Invoice with the rows of the category's tax template where the company holds one, unless
	an invoice with the tag exists."""
	remark = f"MC vat test {tag}"
	if frappe.db.exists("Purchase Invoice", {"remarks": remark, "docstatus": 1}):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Purchase Invoice",
			"company": company,
			"supplier": SUPPLIER,
			"posting_date": date,
			"set_posting_time": 1,
			"bill_no": tag,
			"bill_date": invoiced or date,
			"due_date": date,
			"tax_category": category,
			"remarks": remark,
			"items": [
				{
					"item_name": tag,
					"description": tag,
					"qty": 1,
					"uom": "Nos",
					"conversion_factor": 1,
					"rate": amount,
					"expense_account": account(company, "5100"),
				}
			],
		}
	)
	template = f"{category} - {frappe.get_cached_value('Company', company, 'abbr')}"
	if frappe.db.exists(TEMPLATE, template):
		doc.taxes_and_charges = template
		for row in frappe.get_doc(TEMPLATE, template).taxes:
			doc.append("taxes", {field: row.get(field) for field in TAX_FIELDS})
	doc.insert()
	doc.submit()


def by_key(rows: list[dict]) -> dict[str, dict]:
	return {row["key"]: row for row in rows if row.get("key") and row["key"] != "notice"}


class TestVATRegistration(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.setup = setup_company(
			company_name="MC Test VSE",
			abbr="VSE",
			vat_article=11,
			tax_id="1234-5678",
			fiscal_years=YEARS,
			vat_registered_from="2029-01-01",
			article_12_number="MT12345678",
			article_12_from="2029-03-01",
		)
		cls.company = cls.setup["company"]
		ensure_party("Customer", CUSTOMER)
		ensure_party("Supplier", SUPPLIER)
		sale("malta 1", cls.company, "2030-02-01", SERVICES_MALTA, 5000, "4300")
		sale("eu 1", cls.company, "2030-03-01", SERVICES_EU, 2000, "4100")
		sale("malta 2", cls.company, "2030-09-15", SERVICES_MALTA, 31000, "4300")
		purchase("stock", cls.company, "2030-02-10", STOCK, 400)
		purchase("capital", cls.company, "2030-03-10", CAPITAL, 999)
		purchase("expense", cls.company, "2030-03-12", NO_BOX, 70)
		purchase("eu service", cls.company, "2030-03-10", A12_EU_SERVICES, 100)
		purchase("non-eu service", cls.company, "2030-04-02", A12_NON_EU_SERVICES, 50, invoiced="2030-03-30")
		purchase("eu stock", cls.company, "2030-06-10", A12_STOCK, 200)
		journal("vat payment", cls.company, "2030-05-10", "2220", "3200", 20)

	def setUp(self):
		frappe.set_user("Administrator")

	def test_1_setup(self):
		for category in (*ARTICLE_11, *ARTICLE_12):
			self.assertTrue(frappe.db.exists("Tax Category", category.title), category.title)
		for category in ARTICLE_12:
			template = frappe.get_doc(TEMPLATE, f"{category.title} - VSE")
			self.assertEqual(
				[(row.account_head, row.add_deduct_tax, row.rate) for row in template.taxes],
				[
					(account(self.company, "5960"), "Add", category.rate),
					(account(self.company, "2220"), "Deduct", category.rate),
				],
			)
		self.assertFalse(frappe.db.exists(TEMPLATE, "VAT Box 31/37 Malta services and overheads 18% - VSE"))
		self.assertFalse(frappe.db.exists(TEMPLATE, f"{STOCK} - VSE"))
		record = registration.get(self.company)
		self.assertEqual(
			[(row.article, row.registration_number, str(row.from_date)) for row in record.registrations],
			[("Article 11", "1234-5678", "2029-01-01"), ("Article 12", "MT12345678", "2029-03-01")],
		)
		self.assertEqual(record.activity, "Other activities")
		self.assertEqual(registration.article_on(record, frappe.utils.getdate("2030-06-01")), "Article 11")
		self.assertIsNone(registration.article_on(record, frappe.utils.getdate("2028-12-31")))
		self.assertEqual(str(registration.started(record)), "2029-01-01")

	def test_2_self_charged_vat_is_a_cost(self):
		self.assertEqual(balance(self.company, "2220"), -17.0)
		self.assertEqual(balance(self.company, "5960"), 37.0)
		self.assertEqual(balance(self.company, "1320"), 0.0)

	def test_3_declaration(self):
		_columns, rows, note = vat_declaration_article_11_malta.execute(
			{"company": self.company, "year": 2030}
		)
		row = by_key(rows)
		self.assertEqual([row[f"box_{box}"]["amount"] for box in "1234"], [0.0, 38000.0, 610.0, 999.0])
		current = row["turnover_2030-12-31"]
		self.assertEqual((current["amount"], current["limit"], current["exceeded"]), (36000.0, 35000.0, 1))
		self.assertIn("15", current["status"])
		preceding = row["turnover_2029-12-31"]
		self.assertEqual((preceding["amount"], preceding["exceeded"]), (0.0, 0))
		acquired = row["acquisitions"]
		self.assertEqual((acquired["amount"], acquired["limit"], acquired["exceeded"]), (200.0, 10000.0, 0))
		self.assertIn("Article 11 (1234-5678) from 2029-01-01", note)
		self.assertIn("Article 12 (MT12345678) from 2029-03-01", note)
		self.assertNotIn("art. 12(3a)", note)
		self.assertNotIn("without a tax category", note)

	def test_4_declaration_with_invoices(self):
		_columns, rows, _note = vat_declaration_article_11_malta.execute(
			{"company": self.company, "year": 2030, "show_invoices": 1}
		)
		invoices = [r for r in rows if r.get("kind") == "invoice"]
		self.assertEqual(len(invoices), 6)
		self.assertEqual(sorted(r["amount"] for r in invoices), [210.0, 400.0, 999.0, 2000.0, 5000.0, 31000.0])

	def test_5_article_12(self):
		_columns, rows, note = vat_article_12_malta.execute(
			{"company": self.company, "year": 2030, "as_of": "2030-12-31"}
		)
		notices = [r for r in rows if r.get("key") == "notice"]
		self.assertEqual(
			[(r["supply"], r["from_eu"], r["value"], r["vat"], str(r["due"])) for r in notices],
			[
				("Services", "Yes", 100.0, 18.0, "2030-05-15"),
				("Services", "No", 50.0, 9.0, "2030-05-15"),
				("Goods", "Yes", 200.0, 10.0, "2030-07-15"),
			],
		)
		self.assertEqual([(r["paid"], r["open"]) for r in notices], [(18.0, 0.0), (2.0, 7.0), (0.0, 10.0)])
		self.assertEqual(str(notices[1]["invoice_date"]), "2030-03-30")
		row = by_key(rows)
		total = row["notices_total"]
		self.assertEqual((total["value"], total["vat"], total["paid"], total["open"]), (350.0, 37.0, 20.0, 17.0))
		self.assertEqual((row["eu_services"]["value"], row["eu_services"]["vat"]), (100.0, 18.0))
		self.assertEqual((row["non_eu_services"]["value"], row["non_eu_services"]["vat"]), (50.0, 9.0))
		self.assertEqual((row["acquisitions"]["value"], row["acquisitions"]["vat"]), (200.0, 10.0))
		self.assertEqual((row["annual_total"]["value"], row["annual_total"]["vat"]), (350.0, 37.0))
		self.assertIn("17.00", note)
		self.assertIn("0.6%", note)

	def test_6_payments_as_of_an_earlier_day(self):
		_columns, rows, _note = vat_article_12_malta.execute(
			{"company": self.company, "year": 2030, "as_of": "2030-05-09"}
		)
		self.assertEqual(by_key(rows)["notices_total"]["paid"], 0.0)

	def test_7_registrations_exclude_each_other(self):
		def record(*rows):
			return frappe.get_doc(
				{
					"doctype": "Malta VAT Registration",
					"company": self.company,
					"registrations": [
						{"article": article, "from_date": first, "to_date": last} for article, first, last in rows
					],
				}
			)

		record(("Article 10", "2020-01-01", "2024-12-31"), ("Article 11", "2025-01-01", None)).validate()
		record(("Article 11", "2025-01-01", None), ("Article 12", "2025-06-01", None)).validate()
		for rows in (
			(("Article 10", "2020-01-01", None), ("Article 11", "2025-01-01", None)),
			(("Article 10", None, None), ("Article 12", "2025-06-01", None)),
			(("Article 11", None, "2025-06-30"), ("Article 11", "2025-06-30", None)),
			(("Article 11", "2025-06-30", "2025-01-01"),),
		):
			with self.assertRaises(frappe.ValidationError):
				record(*rows).validate()

	def test_8_patch_creates_the_record_of_an_article_10_company(self):
		company = setup_company(
			company_name="MC Test VTN", abbr="VTN", vat_article=10, tax_id="MT87654321", fiscal_years=YEARS
		)["company"]
		frappe.delete_doc("Malta VAT Registration", company, force=True)
		vat_registrations.execute()
		record = registration.get(company)
		self.assertEqual(
			[(row.article, row.registration_number, row.from_date) for row in record.registrations],
			[("Article 10", "MT87654321", None)],
		)
		self.assertEqual(registration.article_on(record, frappe.utils.getdate("2030-01-01")), "Article 10")
		self.assertFalse(frappe.db.exists(TEMPLATE, f"{A12_EU_SERVICES} - VTN"))

	def test_9_company_without_a_record(self):
		company = setup_company(
			company_name="MC Test VNR", abbr="VNR", vat_article=11, fiscal_years=YEARS
		)["company"]
		frappe.delete_doc("Malta VAT Registration", company, force=True)
		for module in (vat_declaration_article_11_malta, vat_article_12_malta):
			with self.assertRaises(frappe.ValidationError):
				module.execute({"company": company, "year": 2030})
