"""The tax categories of the registrations under Articles 11 and 12 (vat/categories.py), and a Malta VAT
Registration for every company holding Article 10 templates of the app and no such record: one registration under
Article 10 with the Tax ID of the company as its number and no first day. A company without such templates
receives no record; its registration is entered under Malta VAT Registration.
"""

import frappe

from malta_compliance.patches.v0_5.vat_categories import has_templates
from malta_compliance.setup import vat


def execute():
	vat.ensure_tax_categories()
	frappe.db.commit()
	for company in frappe.get_all("Company", pluck="name"):
		if not has_templates(company):
			print(f"malta_compliance: company {company} holds no Article 10 templates; no Malta VAT Registration")
			continue
		number = frappe.db.get_value("Company", company, "tax_id")
		if vat.ensure_registration(company, 10, number):
			print(f"malta_compliance: Malta VAT Registration created for company {company} under Article 10")
	frappe.db.commit()
