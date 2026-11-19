"""A Malta Taxpayer for every taxpayer name of the Malta Tax Year records without one: the field Taxpayer of Malta
Tax Year links to Malta Taxpayer from v0.4.1. The new record carries the tax status of the latest year record and
no dates, companies or returns, so no year is built from it.
"""

import frappe


def execute():
	for row in frappe.get_all(
		"Malta Tax Year", fields=["taxpayer", "status"], order_by="basis_year desc, modified desc"
	):
		if not row.taxpayer or frappe.db.exists("Malta Taxpayer", row.taxpayer):
			continue
		frappe.get_doc(
			{"doctype": "Malta Taxpayer", "taxpayer_name": row.taxpayer, "status": row.status or "Single"}
		).insert(ignore_permissions=True)
		print(f"malta_compliance: Malta Taxpayer {row.taxpayer} created for its Malta Tax Year records")
