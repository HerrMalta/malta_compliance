"""The Journal Entry fields of the VAT settlement, and the new names of renamed tax categories (categories.RENAMED):
the tax category of Maltese supplies at 5% follows boxes 19/24 of the return form. Renaming updates the documents
linking the category; the tax templates of the category receive the new title and the name "<title> - <abbr>".
"""

import frappe

from malta_compliance.setup import vat
from malta_compliance.vat.categories import RENAMED

TEMPLATE_DOCTYPES = ("Sales Taxes and Charges Template", "Purchase Taxes and Charges Template")


def execute():
	vat.ensure_custom_fields()
	for old, (new, _version) in RENAMED.items():
		if not frappe.db.exists("Tax Category", old):
			continue
		if frappe.db.exists("Tax Category", new):
			print(f"malta_compliance: tax categories {old} and {new} both exist; {old} not renamed")
			continue
		frappe.rename_doc("Tax Category", old, new, force=True, show_alert=False)
		frappe.db.set_value("Tax Category", new, "title", new)
		for doctype in TEMPLATE_DOCTYPES:
			for name, company in frappe.get_all(
				doctype, filters={"title": old}, fields=["name", "company"], as_list=True
			):
				target = f"{new} - {frappe.get_cached_value('Company', company, 'abbr')}"
				if name != target:
					if frappe.db.exists(doctype, target):
						print(f"malta_compliance: {doctype} {target} exists; {name} not renamed")
						continue
					frappe.rename_doc(doctype, name, target, force=True, show_alert=False)
				frappe.db.set_value(doctype, target, "title", new)
				print(f"malta_compliance: {doctype} {name} renamed to {target}")
		frappe.db.commit()
		print(f"malta_compliance: tax category {old} renamed to {new}")
