import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from malta_compliance.tax import books
from malta_compliance.tax import year as tax_year


class MaltaTaxYear(Document):
	"""Return data of one taxpayer, or of a married couple, for one basis year: tax status, the companies in the
	books, amounts outside the books and payments. The reports "Income Tax Computation Malta", "Provisional Tax
	Malta" and "Social Security Contributions Malta" compute from it (docs/income-tax.md)."""

	def validate(self):
		if not (self.basis_year or "").isdigit() or len(self.basis_year) != 4:
			frappe.throw(_("Basis Year is a calendar year with four digits"))
		self.year_of_assessment = str(int(self.basis_year) + 1)
		if self.status != "Married":
			for row in [*self.companies, *self.items, *self.payments]:
				if row.person == tax_year.SPOUSE:
					frappe.throw(
						_("Row {0} of table {1} names the spouse, but the tax status is {2}").format(
							row.idx, row.parentfield, self.status
						)
					)
		companies = [row.company for row in self.companies]
		if len(set(companies)) != len(companies):
			frappe.throw(_("A company is listed twice"))

	@frappe.whitelist()
	def fetch_payments(self) -> int:
		"""Appends the payments booked on the accounts 3210 and 3220 of the listed companies from 1 January of the
		basis year to 31 December of the following year, unless a Malta Tax Year lists them already. A payment on
		3220 dated in the basis year is proposed as Class 2 contribution; every other row is added without a kind
		and is not counted until one is chosen. Returns the number of rows added."""
		self.check_permission("write")
		year = int(self.basis_year)
		persons = {row.company: row.person for row in self.companies}
		listed = {
			(row.voucher_no, row.account)
			for row in frappe.get_all(
				"Malta Tax Year Payment",
				filters={"voucher_no": ["is", "set"]},
				fields=["voucher_no", "account"],
			)
		}
		listed |= {(row.voucher_no, row.account) for row in self.payments if row.voucher_no}
		added = 0
		for payment in books.payments(list(persons), getdate(f"{year}-01-01"), getdate(f"{year + 1}-12-31")):
			if (payment.voucher_no, payment.account) in listed:
				continue
			class2 = (
				payment.account_number == books.CLASS2_PAYMENTS and getdate(payment.posting_date).year == year
			)
			self.append(
				"payments",
				{
					"posting_date": payment.posting_date,
					"kind": tax_year.CLASS2 if class2 else "",
					"person": persons[payment.company],
					"amount": payment.amount,
					"account": payment.account,
					"voucher_type": payment.voucher_type,
					"voucher_no": payment.voucher_no,
					"remarks": payment.remarks,
				},
			)
			added += 1
		if added:
			self.save()
		return added
