"""Integration tests of the desk entry on a test site: the Dock record of the app mounted on ERPNext's rail, and the
icons named by that record and by the sidebar "Malta Compliance". Read-only; runs after the app is installed.

Run: bench --site <test site> run-tests --module malta_compliance.tests.test_desk
"""

import unittest

import frappe
from frappe.boot import get_app_data
from frappe.desk.doctype.dock.dock import get_app_entry_set, mounted_apps

SIDEBAR = "Malta Compliance"
ICON_HOOK = "/assets/malta_compliance/icons/module-icons.svg"


class TestDesk(unittest.TestCase):
	def test_mounted_on_erpnext(self):
		self.assertEqual(mounted_apps().get("malta_compliance"), "erpnext")

	def test_entry_on_erpnext_rail(self):
		entries = [
			entry
			for entry in get_app_entry_set("erpnext")
			if entry["link_type"] == "Sidebar" and entry["link_to"] == SIDEBAR
		]
		self.assertEqual(len(entries), 1)
		self.assertEqual(entries[0]["title"], SIDEBAR)

	def test_no_apps_screen_tile(self):
		app = next(app for app in get_app_data() if app["app_name"] == "malta_compliance")
		self.assertFalse(app["on_apps_screen"])

	def test_icons_in_sprite(self):
		self.assertIn(ICON_HOOK, frappe.get_hooks("app_include_icons", app_name="malta_compliance"))
		path = frappe.get_app_path("malta_compliance", "public", "icons", "module-icons.svg")
		with open(path, encoding="utf-8") as sprite:
			symbols = sprite.read()
		icons = [row.icon for row in frappe.get_doc("Dock", "malta_compliance").items]
		icons.append(frappe.db.get_value("Sidebar", SIDEBAR, "header_icon"))
		for icon in icons:
			self.assertIn(f'id="icon-{icon}"', symbols)
