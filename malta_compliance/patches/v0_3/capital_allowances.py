"""Capital allowances for every company set up by the app: missing chart accounts, Asset Categories, their account
rows and the fixed-asset Items. A company set up by the app is recognised by account 1590 "Accumulated Capital
Allowances"; a company with another chart is skipped with a logged message.
"""

import frappe

from malta_compliance.setup import capital_allowances
from malta_compliance.setup.company import ensure_chart_accounts


def execute():
	capital_allowances.ensure_custom_fields()
	for company in frappe.get_all("Company", pluck="name"):
		marker = frappe.db.get_value(
			"Account",
			{"company": company, "account_number": "1590", "account_type": "Accumulated Depreciation"},
			"account_name",
		)
		if marker != "Accumulated Capital Allowances":
			print(
				f"malta_compliance: company {company} has no chart of the app; capital allowances not set up"
			)
			continue
		try:
			ensure_chart_accounts(company)
			result = capital_allowances.setup_capital_allowances(company, create_fields=False)
		except frappe.ValidationError as e:
			frappe.db.rollback()
			print(f"malta_compliance: capital allowances not set up for company {company}: {e}")
			continue
		frappe.db.commit()
		print(f"malta_compliance: capital allowances set up for company {company}: {result}")
