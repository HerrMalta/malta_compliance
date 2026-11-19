import frappe
from frappe import _
from frappe.model.document import Document

from malta_compliance.tax import income_tax
from malta_compliance.tax import year as tax_year


class MaltaTaxpayer(Document):
	"""Facts of a taxpayer or a married couple that hold for every year: tax status, year of birth and self-occupation
	of each person, the companies in the books and the returns as filed. The report "Tax Payments Malta" builds the
	figures of a year from it where no Malta Tax Year record of the year exists (docs/income-tax.md)."""

	def validate(self):
		years = [row.basis_year for row in self.returns]
		for basis_year in years:
			if not (basis_year or "").isdigit() or len(basis_year) != 4:
				frappe.throw(
					_("Basis Year {0} of the returns is not a calendar year with four digits").format(
						basis_year
					)
				)
		if len(set(years)) != len(years):
			frappe.throw(_("A return is listed twice for the same basis year"))
		companies = [row.company for row in self.companies]
		if len(set(companies)) != len(companies):
			frappe.throw(_("A company is listed twice"))
		if self.status != income_tax.MARRIED and any(row.person == tax_year.SPOUSE for row in self.companies):
			frappe.throw(_("A company names the spouse, but the tax status is {0}").format(self.status))
		for company in companies:
			other = frappe.db.get_value(
				"Malta Tax Year Company",
				{"parenttype": self.doctype, "company": company, "parent": ["!=", self.name or ""]},
				"parent",
			)
			if other:
				frappe.throw(_("Company {0} is listed by the Malta Taxpayer {1}").format(company, other))
		for prefix in ("self", "spouse"):
			start, end = self.get(f"{prefix}_occupied_from"), self.get(f"{prefix}_occupied_until")
			if start and end and end < start:
				frappe.throw(_("The self-occupation ends before it starts"))
