"""Check of the schedule override after every migration (after_migrate). An ERPNext release that renames or changes
one of the overridden methods would silently bring back ERPNext's pro-rata rows; the check computes three schedules
in memory and stops the migration when a row differs. The release then fails in the staging test of the pipeline.
"""

import frappe
from erpnext.accounts.utils import FiscalYearError
from erpnext.assets.doctype.asset_depreciation_schedule.deppreciation_schedule_controller import (
	DepreciationScheduleController,
)
from frappe.utils import flt, getdate

from malta_compliance.assets.schedule import OVERRIDDEN_METHODS, MaltaAssetDepreciationSchedule

CATEGORY = "CA 01 Computers and Electronic Equipment"
EXPECTED = [("2025-12-31", 500.0), ("2026-12-31", 500.0), ("2027-12-31", 500.0), ("2028-12-31", 500.0)]


def run() -> None:
	missing = [
		m for m in (*OVERRIDDEN_METHODS, "create", "clear") if not hasattr(DepreciationScheduleController, m)
	]
	if missing:
		frappe.throw(f"malta_compliance self-check: ERPNext no longer has the methods {missing}")
	if frappe.get_hooks("override_doctype_class", {}).get("Asset Depreciation Schedule", [None])[-1] != (
		"malta_compliance.assets.schedule.MaltaAssetDepreciationSchedule"
	):
		frappe.throw("malta_compliance self-check: another app overrides Asset Depreciation Schedule")
	company = frappe.db.get_value("Asset Category Account", {"parent": CATEGORY}, "company_name")
	if not company:
		return
	checks = (
		(None, [], EXPECTED),
		("2027-03-10", EXPECTED[:2], EXPECTED[:2]),
		("2026-12-31", EXPECTED[:1], EXPECTED[:2]),
	)
	for disposal_date, booked, expected in checks:
		try:
			rows = compute(company, disposal_date, booked)
		except FiscalYearError:
			return

		if rows != expected:
			frappe.throw(
				f"malta_compliance self-check: schedule rows {rows} instead of {expected} "
				f"(disposal {disposal_date}); the ERPNext override needs review"
			)


def compute(company: str, disposal_date: str | None, booked: list) -> list:
	"""Rows of a computer of EUR 2,000 first used on 2025-06-15, with the given rows already booked."""
	asset = frappe.new_doc("Asset")
	asset.update(
		{
			"company": company,
			"asset_category": CATEGORY,
			"item_code": CATEGORY,
			"net_purchase_amount": 2000,
			"purchase_date": getdate("2025-06-15"),
			"available_for_use_date": getdate("2025-06-15"),
			"calculate_depreciation": 1,
			"opening_accumulated_depreciation": 0,
			"opening_number_of_booked_depreciations": 0,
			"additional_asset_cost": 0,
		}
	)
	fb = asset.append(
		"finance_books",
		{
			"depreciation_method": "Straight Line",
			"total_number_of_depreciations": 4,
			"frequency_of_depreciation": 12,
			"depreciation_start_date": getdate("2025-12-31"),
			"value_after_depreciation": 2000,
			"expected_value_after_useful_life": 0,
		},
	)
	schedule = MaltaAssetDepreciationSchedule({"doctype": "Asset Depreciation Schedule"})
	schedule.asset_doc = asset
	schedule.fb_row = fb
	schedule.disposal_date = getdate(disposal_date) if disposal_date else None
	for date, amount in booked:
		schedule.append(
			"depreciation_schedule",
			{"schedule_date": getdate(date), "depreciation_amount": amount, "journal_entry": "self-check"},
		)
	fb.value_after_depreciation = 2000 - sum(amount for _date, amount in booked)
	schedule.fetch_asset_details()
	schedule.clear()
	schedule.create()
	return [
		(str(getdate(r.schedule_date)), flt(r.depreciation_amount)) for r in schedule.depreciation_schedule
	]
