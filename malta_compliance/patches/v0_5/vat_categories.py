"""The tax categories of every line of the VAT return (vat/categories.py) and, on every company holding Article 10
templates of these categories, the missing templates with the chart accounts they post to. A company without such
templates (Article 11, or another chart) receives the categories only.
"""

import frappe

from malta_compliance.setup import vat
from malta_compliance.setup.company import ensure_chart_accounts
from malta_compliance.vat.categories import CATEGORIES

TEMPLATE_DOCTYPES = ("Sales Taxes and Charges Template", "Purchase Taxes and Charges Template")


def has_templates(company: str) -> bool:
	titles = [title for title, *_ in CATEGORIES]
	return any(
		frappe.get_all(doctype, filters={"company": company, "tax_category": ["in", titles]}, limit=1)
		for doctype in TEMPLATE_DOCTYPES
	)


def execute():
	vat.ensure_tax_categories()
	frappe.db.commit()
	for company in frappe.get_all("Company", pluck="name"):
		if not has_templates(company):
			print(f"malta_compliance: company {company} holds no Article 10 templates of the app; none added")
			continue
		try:
			accounts = ensure_chart_accounts(company)
			created = vat.ensure_templates(company)
		except frappe.ValidationError as e:
			frappe.db.rollback()
			print(f"malta_compliance: VAT templates not added for company {company}: {e}")
			continue
		frappe.db.commit()
		print(f"malta_compliance: company {company}: accounts added {accounts}, templates added {created}")
