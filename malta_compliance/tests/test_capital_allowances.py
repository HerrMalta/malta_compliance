"""Integration tests of the Maltese capital allowance rules (docs/capital-allowances.md) on a test site. Each test
class sets up its own company with setup_company; dates lie before 2026-11-18, because ERPNext rejects scrapping on
future dates.

Run: bench --site <test site> run-tests --module malta_compliance.tests.test_capital_allowances
"""

import unittest

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
from erpnext.assets.doctype.asset.depreciation import _make_depreciation_entry, scrap_asset
from erpnext.assets.doctype.asset_depreciation_schedule.asset_depreciation_schedule import (
	get_asset_depr_schedule_name,
	get_depr_schedule,
)
from frappe.utils import flt, getdate

from malta_compliance.assets import allowance, rules, selfcheck
from malta_compliance.setup import capital_allowances
from malta_compliance.setup.company import ensure_chart_accounts, setup_company
from malta_compliance.setup.vat import account

COMPUTER = "CA 01 Computers and Electronic Equipment"
SOFTWARE = "CA 02 Computer Software"
VEHICLE = "CA 03 Motor Vehicles"
AIRCRAFT = "CA 07 Aircraft Airframes, Engines, Overhauls and Interiors"
IP = "CA IP Intellectual Property"
BUILDING = "CA IB Industrial Buildings and Structures"
CUSTOMER = "MC Test Customer"


def make_company(abbr: str, first_year: int = 2020) -> str:
	frappe.set_user("Administrator")
	result = setup_company(
		company_name=f"MC Test {abbr}", abbr=abbr, vat_article=10, fiscal_years=list(range(first_year, 2032))
	)
	return result["company"]


def make_asset(company: str, category: str, cost: float, first_use: str, submit: bool = True, **fields):
	doc = frappe.get_doc(
		{
			"doctype": "Asset",
			"asset_name": f"{category} {cost} {first_use}",
			"item_code": category,
			"company": company,
			"location": company,
			"purchase_date": fields.pop("purchase_date", first_use),
			"available_for_use_date": first_use,
			"net_purchase_amount": cost,
			"purchase_amount": cost,
			**fields,
		}
	)
	doc.insert()
	if submit:
		doc.submit()
	return frappe.get_doc("Asset", doc.name)


def rows(asset_name: str) -> list[tuple]:
	schedule = get_depr_schedule(asset_name, ["Active", "Draft"])
	return [(str(getdate(r.schedule_date)), flt(r.depreciation_amount)) for r in schedule]


def book(asset_name: str, date: str) -> None:
	name = get_asset_depr_schedule_name(asset_name, "Active")[0].name
	_make_depreciation_entry(name, date)


def balance(company: str, number: str, voucher: str | None = None) -> float:
	"""Debit minus credit on an account, optionally of one voucher and its app adjustments."""
	conditions, values = "", [account(company, number)]
	if voucher:
		adjustments = frappe.get_all(
			"Journal Entry", filters={"mc_adjustment_for": voucher, "docstatus": 1}, pluck="name"
		)
		conditions = " and voucher_no in %s"
		values.append(tuple([voucher, *adjustments]))
	result = frappe.db.sql(
		f"select sum(debit - credit) from `tabGL Entry` where account = %s and is_cancelled = 0{conditions}",
		values,
	)
	return flt(result[0][0], 2)


def sell(company: str, asset_name: str, date: str, amount: float):
	if not frappe.db.exists("Customer", CUSTOMER):
		frappe.get_doc(
			{"doctype": "Customer", "customer_name": CUSTOMER, "customer_type": "Company"}
		).insert()
	asset = frappe.get_doc("Asset", asset_name)
	si = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": company,
			"customer": CUSTOMER,
			"posting_date": date,
			"set_posting_time": 1,
			"due_date": date,
			"items": [
				{
					"item_code": asset.item_code,
					"asset": asset_name,
					"qty": 1,
					"rate": amount,
					"income_account": account(company, "4910"),
				}
			],
		}
	)
	si.insert()
	si.submit()
	return si


def depreciation_entries(asset_name: str) -> list[str]:
	return [r.journal_entry for r in get_depr_schedule(asset_name, "Active") if r.journal_entry]


class TestRules(unittest.TestCase):
	def test_register_versions(self):
		self.assertEqual(rules.wear_and_tear_years(1, getdate("2025-06-15"), getdate("2025-06-15")).value, 4)
		self.assertEqual(rules.select(rules.PLANT_INITIAL_RATE, getdate("2001-03-01")).value, 0)
		self.assertEqual(rules.select(rules.PLANT_INITIAL_RATE, getdate("2000-03-01")).value, 20)
		with self.assertRaises(rules.NotCovered):
			rules.wear_and_tear_years(7, getdate("2019-01-01"), getdate("2017-06-30"))
		with self.assertRaises(rules.NotCovered):
			rules.select(rules.IP_ONE_YEAR, getdate("2022-12-31"))

	def test_review_warning(self):
		self.assertIsNone(rules.review_warning(rules.REVIEWED_UP_TO - 1))
		self.assertIn(str(rules.REVIEWED_UP_TO + 1), rules.review_warning(rules.REVIEWED_UP_TO))

	def test_building_years(self):
		self.assertEqual(capital_allowances.building_years(True, getdate("2025-01-01")), 45)
		self.assertEqual(capital_allowances.building_years(False, getdate("2025-01-01")), 50)


class TestSetup(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.company = make_company("MCS")

	def test_setup_is_idempotent(self):
		self.assertEqual(ensure_chart_accounts(self.company), [])
		result = capital_allowances.setup_capital_allowances(self.company)
		self.assertEqual(result, {"categories": 0, "items": 0})
		self.assertEqual(len(capital_allowances.CATEGORIES), 21)
		for name, *_ in capital_allowances.CATEGORIES:
			self.assertTrue(
				frappe.db.exists("Item", {"name": name, "is_fixed_asset": 1, "asset_category": name})
			)

	def test_selfcheck(self):
		selfcheck.run()

	def test_patch_on_company_of_version_0_2(self):
		"""A company set up with the chart of 0.2.0 receives the new accounts, the category rows and the Items."""
		import json
		import os
		import tempfile

		from malta_compliance.patches.v0_3 import capital_allowances as patch
		from malta_compliance.setup import company as company_setup

		with open(company_setup.CHART_FILE) as f:
			chart = json.load(f)
		fixed = chart["Assets"]["Fixed Assets"]
		for name in (
			"Computer Software",
			"Plant and Machinery",
			"Installations in Premises",
			"Intellectual Property",
			"Industrial Buildings and Structures",
			"Land",
		):
			del fixed[name]
		del chart["Equity"]["Owner Equity"]["Non-deductible Capital Allowances"]
		for name in ("Capital Allowances Intellectual Property", "Capital Allowances Industrial Buildings"):
			del chart["Expenses"]["Capital Allowances"][name]
		saved = company_setup.CHART_FILE
		with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
			json.dump(chart, f)
		try:
			company_setup.CHART_FILE = f.name
			suffix = frappe.generate_hash(length=5).upper()
			company, _created = company_setup.ensure_company(
				f"MC Test Old {suffix}", f"O{suffix}", None, None, None
			)
		finally:
			company_setup.CHART_FILE = saved
			os.unlink(f.name)
		self.assertFalse(frappe.db.exists("Account", {"company": company.name, "account_number": "1540"}))
		patch.execute()
		for number in ("1540", "1550", "1560", "1570", "1580", "1585", "3240", "6110", "6120"):
			self.assertTrue(
				frappe.db.exists("Account", {"company": company.name, "account_number": number}), number
			)
		self.assertTrue(
			frappe.db.exists("Asset Category Account", {"parent": SOFTWARE, "company_name": company.name})
		)


class TestWearAndTear(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.company = make_company("MCW")

	def test_full_first_year(self):
		asset = make_asset(self.company, COMPUTER, 2000, "2025-06-15")
		self.assertEqual(
			rows(asset.name),
			[("2025-12-31", 500.0), ("2026-12-31", 500.0), ("2027-12-31", 500.0), ("2028-12-31", 500.0)],
		)
		self.assertIn("WT01@2001-01-01", asset.mc_rule_version)

	def test_rounding_in_last_row(self):
		asset = make_asset(self.company, COMPUTER, 1000, "2024-02-01", submit=False)
		amounts = [a for _d, a in rows(asset.name)]
		self.assertEqual(amounts, [250.0] * 4)
		asset = make_asset(self.company, SOFTWARE, 1001, "2024-02-01", submit=False)
		amounts = [a for _d, a in rows(asset.name)]
		self.assertEqual(round(sum(amounts), 2), 1001.0)
		self.assertEqual(len(amounts), 4)

	def test_minimum_years(self):
		with self.assertRaises(frappe.ValidationError):
			make_asset(
				self.company,
				COMPUTER,
				2000,
				"2025-06-15",
				submit=False,
				finance_books=[{"total_number_of_depreciations": 3, "frequency_of_depreciation": 12}],
			)
		asset = make_asset(
			self.company,
			COMPUTER,
			2000,
			"2025-06-15",
			submit=False,
			finance_books=[{"total_number_of_depreciations": 5, "frequency_of_depreciation": 12}],
		)
		self.assertEqual([a for _d, a in rows(asset.name)], [400.0] * 5)

	def test_not_covered(self):
		with self.assertRaises(frappe.ValidationError):
			make_asset(self.company, COMPUTER, 2000, "2000-06-15", submit=False)
		with self.assertRaises(frappe.ValidationError):
			make_asset(self.company, AIRCRAFT, 50000, "2019-01-10", submit=False, purchase_date="2017-06-30")

	def test_disposal_mid_year(self):
		asset = make_asset(self.company, COMPUTER, 2000, "2023-06-15")
		book(asset.name, "2024-12-31")
		si = sell(self.company, asset.name, "2025-03-10", 900)
		self.assertEqual(rows(asset.name), [("2023-12-31", 500.0), ("2024-12-31", 500.0)])
		self.assertEqual(balance(self.company, "6200", si.name), 100.0)
		self.assertFalse(frappe.db.exists("Journal Entry", {"mc_adjustment_for": si.name, "docstatus": 1}))
		si.reload()
		si.cancel()
		self.assertEqual(
			rows(asset.name),
			[("2023-12-31", 500.0), ("2024-12-31", 500.0), ("2025-12-31", 500.0), ("2026-12-31", 500.0)],
		)

	def test_disposal_on_year_end(self):
		asset = make_asset(self.company, COMPUTER, 2000, "2023-06-15")
		book(asset.name, "2023-12-31")
		sell(self.company, asset.name, "2024-12-31", 900)
		self.assertEqual(rows(asset.name), [("2023-12-31", 500.0), ("2024-12-31", 500.0)])

	def test_disposal_on_year_end_with_row_booked(self):
		asset = make_asset(self.company, COMPUTER, 2000, "2023-06-15")
		book(asset.name, "2024-12-31")
		sell(self.company, asset.name, "2024-12-31", 900)
		self.assertEqual(rows(asset.name), [("2023-12-31", 500.0), ("2024-12-31", 500.0)])

	def test_sale_before_booked_year_end(self):
		asset = make_asset(self.company, COMPUTER, 2000, "2023-06-15")
		book(asset.name, "2024-12-31")
		with self.assertRaises(frappe.ValidationError):
			sell(self.company, asset.name, "2024-03-10", 1200)
		last = depreciation_entries(asset.name)[-1]
		frappe.get_doc("Journal Entry", last).cancel()
		sell(self.company, asset.name, "2024-03-10", 1200)
		self.assertEqual(rows(asset.name), [("2023-12-31", 500.0)])

	def test_balancing_charge_limited_to_allowances(self):
		asset = make_asset(self.company, COMPUTER, 2000, "2023-06-15")
		book(asset.name, "2023-12-31")
		si = sell(self.company, asset.name, "2024-02-01", 2500)
		self.assertEqual(balance(self.company, "6200", si.name), -500.0)
		self.assertEqual(balance(self.company, "3240", si.name), -500.0)

	def test_purchase_and_sale_in_same_year(self):
		asset = make_asset(self.company, COMPUTER, 2000, "2025-02-01")
		si = sell(self.company, asset.name, "2025-10-01", 1200)
		self.assertEqual(rows(asset.name), [])
		self.assertEqual(balance(self.company, "6200", si.name), 0.0)
		self.assertEqual(balance(self.company, "3240", si.name), 800.0)

	def test_existing_asset(self):
		asset = make_asset(
			self.company,
			COMPUTER,
			2000,
			"2021-06-15",
			submit=False,
			asset_type="Existing Asset",
			opening_number_of_booked_depreciations=2,
		)
		self.assertEqual(flt(asset.opening_accumulated_depreciation), 1000.0)
		self.assertEqual(rows(asset.name), [("2023-12-31", 500.0), ("2024-12-31", 500.0)])
		with self.assertRaises(frappe.ValidationError):
			make_asset(
				self.company,
				COMPUTER,
				2000,
				"2021-06-15",
				submit=False,
				asset_type="Existing Asset",
				opening_number_of_booked_depreciations=2,
				opening_accumulated_depreciation=900,
			)

	def test_value_adjustment_rejected(self):
		asset = make_asset(self.company, COMPUTER, 2000, "2023-06-15")
		doc = frappe.get_doc(
			{
				"doctype": "Asset Value Adjustment",
				"company": self.company,
				"asset": asset.name,
				"date": "2024-06-30",
				"new_asset_value": 1000,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.insert()


class TestVehicle(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.company = make_company("MCV")

	def test_cap_and_private_use(self):
		asset = make_asset(self.company, VEHICLE, 30000, "2022-03-01", mc_business_use=60)
		self.assertAlmostEqual(allowance.cap_ratio(asset, "2022-12-31"), 14000 / 30000)
		book(asset.name, "2022-12-31")
		je = depreciation_entries(asset.name)[0]
		self.assertEqual(balance(self.company, "6100", je), 1680.0)
		self.assertEqual(balance(self.company, "3200", je), 2400.0)
		self.assertEqual(balance(self.company, "3240", je), 1920.0)
		adjustment = frappe.get_all(
			"Journal Entry", filters={"mc_adjustment_for": je, "docstatus": 1}, pluck="name"
		)[0]
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("Journal Entry", adjustment).cancel()
		frappe.get_doc("Journal Entry", je).cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", adjustment, "docstatus"), 2)

	def test_business_use_per_year(self):
		asset = make_asset(
			self.company,
			VEHICLE,
			30000,
			"2022-03-01",
			mc_business_use=60,
			mc_business_use_years=[{"fiscal_year": "2023", "business_use": 50}],
		)
		book(asset.name, "2023-12-31")
		first, second = depreciation_entries(asset.name)[:2]
		self.assertEqual(balance(self.company, "6100", first), 1680.0)
		self.assertEqual(balance(self.company, "6100", second), 1400.0)
		self.assertEqual(balance(self.company, "3200", second), 3000.0)

	def test_capped_vehicle_sale(self):
		asset = make_asset(self.company, VEHICLE, 30000, "2022-03-01", mc_business_use=60)
		book(asset.name, "2023-12-31")
		si = sell(self.company, asset.name, "2024-05-01", 15000)
		self.assertEqual(balance(self.company, "6200", si.name), 840.0)
		self.assertEqual(balance(self.company, "3200", si.name), 1200.0)
		self.assertEqual(balance(self.company, "3240", si.name), 960.0)
		ret = make_sales_return(si.name)
		ret.insert()
		ret.submit()
		self.assertFalse(frappe.db.exists("Journal Entry", {"mc_adjustment_for": si.name, "docstatus": 1}))
		ret.reload()
		ret.cancel()
		self.assertTrue(frappe.db.exists("Journal Entry", {"mc_adjustment_for": si.name, "docstatus": 1}))

	def test_withdrawal_at_market_value(self):
		asset = make_asset(self.company, VEHICLE, 12000, "2022-03-01")
		book(asset.name, "2024-12-31")
		asset.reload()
		asset.db_set("mc_disposal_value", 6000)
		scrap_asset(asset.name, "2025-06-30")
		scrap = frappe.db.get_value("Asset", asset.name, "journal_entry_for_scrap")
		self.assertEqual(balance(self.company, "6200", scrap), -1200.0)
		self.assertEqual(balance(self.company, "3200", scrap), 6000.0)


class TestVehicleBefore2010(unittest.TestCase):
	"""Car bought in 2009 for EUR 20,000: cap 7,000 for basis year 2009, 14,000 from basis year 2010 (year of
	assessment 2011)."""

	@classmethod
	def setUpClass(cls):
		cls.company = make_company("MCO", first_year=2008)

	def test_cap_by_year_of_claim(self):
		asset = make_asset(
			self.company,
			VEHICLE,
			20000,
			"2009-05-01",
			asset_type="Existing Asset",
			opening_number_of_booked_depreciations=2,
		)
		self.assertEqual(flt(asset.opening_accumulated_depreciation), 8000.0)
		book(asset.name, "2011-12-31")
		je = depreciation_entries(asset.name)[0]
		self.assertEqual(balance(self.company, "6100", je), 2800.0)
		si = sell(self.company, asset.name, "2012-06-30", 9000)
		self.assertEqual(balance(self.company, "6200", si.name), 700.0)
		self.assertEqual(balance(self.company, "3240", si.name), -1700.0)


class TestBuildingsAndIP(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.company = make_company("MCB")

	def test_building_condition_required(self):
		with self.assertRaises(frappe.ValidationError):
			make_asset(self.company, BUILDING, 100000, "2024-06-01", submit=False)

	def test_building_with_initial_allowance(self):
		asset = make_asset(
			self.company,
			BUILDING,
			100000,
			"2024-06-01",
			submit=False,
			mc_building_condition=capital_allowances.NEW_BUILDING,
		)
		amounts = [a for _d, a in rows(asset.name)]
		self.assertEqual(len(amounts), 45)
		self.assertEqual(amounts[0], 12000.0)
		self.assertEqual(set(amounts[1:]), {2000.0})

	def test_building_without_initial_allowance(self):
		asset = make_asset(
			self.company,
			BUILDING,
			100000,
			"2024-06-01",
			submit=False,
			mc_building_condition=capital_allowances.USED_BUILDING,
		)
		amounts = [a for _d, a in rows(asset.name)]
		self.assertEqual(len(amounts), 50)
		self.assertEqual(set(amounts), {2000.0})

	def test_ip_spread(self):
		asset = make_asset(self.company, IP, 9000, "2024-04-01", submit=False)
		self.assertEqual([a for _d, a in rows(asset.name)], [3000.0] * 3)
		asset = make_asset(
			self.company,
			IP,
			9000,
			"2024-04-01",
			submit=False,
			finance_books=[{"total_number_of_depreciations": 5, "frequency_of_depreciation": 12}],
		)
		self.assertEqual([a for _d, a in rows(asset.name)], [1800.0] * 5)

	def test_ip_one_year(self):
		asset = make_asset(self.company, IP, 9000, "2024-04-01", mc_ip_one_year=1)
		self.assertEqual(rows(asset.name), [("2024-12-31", 9000.0)])
		with self.assertRaises(frappe.ValidationError):
			make_asset(self.company, IP, 9000, "2022-04-01", submit=False, mc_ip_one_year=1)

	def test_ip_sale_outside_profit(self):
		"""The instalment of the year of sale is deducted; the result of the sale is the art. 5 gain."""
		from malta_compliance.malta_compliance.report.capital_allowances_malta.capital_allowances_malta import (
			execute,
		)

		asset = make_asset(self.company, IP, 9000, "2023-04-01")
		book(asset.name, "2023-12-31")
		si = sell(self.company, asset.name, "2024-05-01", 8000)
		self.assertEqual(rows(asset.name), [("2023-12-31", 3000.0), ("2024-05-01", 3000.0)])
		entries = depreciation_entries(asset.name)
		self.assertEqual([balance(self.company, "6110", je) for je in entries], [3000.0, 3000.0])
		self.assertEqual(balance(self.company, "6200", si.name), 0.0)
		self.assertEqual(balance(self.company, "3240", si.name), -5000.0)
		_columns, data, _message, _chart, _summary = execute({"company": self.company, "fiscal_year": "2024"})
		row = next(r for r in data if r["asset"] == asset.name)
		self.assertEqual(row["deductions_claimed"], 6000.0)
		self.assertEqual(row["reduced_cost"], 3000.0)
		self.assertEqual(row["capital_gain"], 5000.0)


class TestReport(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.company = make_company("MCR")

	def test_report(self):
		from malta_compliance.malta_compliance.report.capital_allowances_malta.capital_allowances_malta import (
			execute,
		)

		asset = make_asset(self.company, VEHICLE, 30000, "2022-03-01", mc_business_use=60)
		book(asset.name, "2023-12-31")
		sell(self.company, asset.name, "2024-05-01", 15000)
		_columns, data, _message, _chart, _summary = execute({"company": self.company, "fiscal_year": "2023"})
		row = next(r for r in data if r["asset"] == asset.name)
		self.assertEqual(row["deductible"], 1680.0)
		self.assertEqual(row["allowance_base"], 14000.0)
		self.assertEqual(row["written_down_value"], 14000.0 - 2 * 2800.0)
		_columns, data, _message, _chart, _summary = execute({"company": self.company, "fiscal_year": "2024"})
		row = next(r for r in data if r["asset"] == asset.name)
		self.assertEqual(row["apportioned_proceeds"], 7000.0)
		self.assertEqual(row["balancing"], -840.0)
