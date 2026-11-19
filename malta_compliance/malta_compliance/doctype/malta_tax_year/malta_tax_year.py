import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from malta_compliance.tax import books
from malta_compliance.tax import taxpayer as taxpayer_record
from malta_compliance.tax import year as tax_year

# Fields of a new record taken from the year built from its Malta Taxpayer.
DEFAULT_FIELDS = (
	"status",
	"children",
	"child_tables",
	*(
		f"{prefix}_{field}"
		for prefix in ("self", "spouse")
		for field in (
			"no_class2",
			"born_before_1962",
			"first_year",
			"active_from",
			"active_to",
			"class2_base_entered",
			"class2_base",
		)
	),
	"filed",
	"filed_tax",
	"filed_chargeable_income",
)


@frappe.whitelist()
def taxpayer_defaults(taxpayer: str, basis_year: str) -> dict:
	"""Values of a new Malta Tax Year from its Malta Taxpayer: the figures the reports build for the year without a
	record, with the companies and the amounts outside the books; empty for a basis year that is not four digits."""
	if not (basis_year or "").isdigit() or len(basis_year) != 4:
		return {}
	master = frappe.get_doc("Malta Taxpayer", taxpayer)
	master.check_permission("read")
	taxpayer_record.clear_cache()
	built = taxpayer_record.build(master, int(basis_year))
	values = {field: built.get(field) for field in DEFAULT_FIELDS}
	values["companies"] = [{"company": row.company, "person": row.person} for row in built.companies]
	values["items"] = [
		{"kind": row.kind, "person": row.person, "description": row.description, "amount": row.amount}
		for row in built.items
	]
	taxpayer_record.clear_cache()
	return values


class MaltaTaxYear(Document):
	"""Return data of one taxpayer, or of a married couple, for one basis year: tax status, the companies in the
	books, amounts outside the books and the payments made in that year. The reports "Income Tax Computation
	Malta", "Provisional Tax Malta" and "Social Security Contributions Malta" compute from it (docs/income-tax.md)."""

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
		if self.pt_reduced and not self.pt_reduced_on:
			frappe.throw(_("Enter the date on which the P.T. Reduction Form was filed"))

	@frappe.whitelist()
	def fetch_payments(self) -> int:
		"""Appends the payments booked in the basis year on the accounts 3210 and 3220 of the listed companies,
		unless a Malta Tax Year lists them already, and returns the number of rows added. Each new row receives its
		kind by account and amount (tax/taxpayer.py, classify); a kind can be changed afterwards."""
		self.check_permission("write")
		taxpayer_record.clear_cache()
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
		for payment in books.payments(list(persons), getdate(f"{year}-01-01"), getdate(f"{year}-12-31")):
			if (payment.voucher_no, payment.account) in listed:
				continue
			self.append(
				"payments",
				{
					"posting_date": payment.posting_date,
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
			taxpayer_record.classify(self, self.payments)
			self.save()
		return added
