import frappe
from frappe import _
from frappe.model.document import Document

from malta_compliance.vat import registration


class MaltaVATRegistration(Document):
	"""VAT registrations of a company: under Article 10 or Article 11 with the dates of each, and under Article 12
	beside Article 11. The reports "VAT Declaration Article 11 Malta" and "VAT Article 12 Malta" read it
	(docs/vat-articles-11-12.md)."""

	def validate(self):
		for row in self.registrations:
			first, last = registration.bounds(row)
			if last < first:
				frappe.throw(_("Row {0}: the registration ends before it starts").format(row.idx))
		for index, row in enumerate(self.registrations):
			first, last = registration.bounds(row)
			for other in self.registrations[index + 1 :]:
				other_first, other_last = registration.bounds(other)
				if not (first <= other_last and other_first <= last):
					continue
				pair = (row.article, other.article)
				excluded = pair in registration.EXCLUSIVE or pair[::-1] in registration.EXCLUSIVE
				if row.article == other.article or excluded:
					frappe.throw(
						_("Rows {0} and {1}: {2} and {3} cover the same days").format(
							row.idx, other.idx, row.article, other.article
						)
					)
