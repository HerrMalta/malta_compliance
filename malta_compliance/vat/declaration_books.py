"""Reads the books of a company for the Article 11 declaration (declaration.py) and the notices of Article 12
(article12.py): the submitted Sales and Purchase Invoices of a period without opening invoices, the held drafts,
and the payments of self-charged VAT. The VAT self-charged on a purchase is the total of its tax rows deducted on
2220 Output VAT Reverse Charge; a debit on that account from any other voucher is a payment.
"""

from collections import defaultdict
from datetime import date

import frappe
from frappe import _
from frappe.utils import getdate

from malta_compliance.vat.books import INVOICE_DOCTYPES, PARTY_FIELD, cents
from malta_compliance.vat.categories import ACCOUNTS
from malta_compliance.vat.declaration import Document

PAYABLE = ACCOUNTS["output_reverse"]


def payable_account(company: str) -> str:
	"""Name of the account holding the self-charged VAT payable."""
	name = frappe.db.get_value("Account", {"company": company, "account_number": PAYABLE, "is_group": 0})
	if not name:
		frappe.throw(
			_("Account {0} is missing in the company {1}; the report needs the chart of the Malta app.").format(
				PAYABLE, company
			)
		)
	return name


def drafts(company: str, first: date, last: date) -> list[str]:
	"""Names of the draft invoices dated from first to last."""
	names = []
	for doctype in INVOICE_DOCTYPES:
		names += frappe.get_all(
			doctype,
			filters={"company": company, "posting_date": ["between", [first, last]], "docstatus": 0},
			pluck="name",
			order_by="name",
		)
	return names


def documents(company: str, first: date, last: date) -> list[Document]:
	"""The submitted invoices posted from first to last, in date order."""
	payable = payable_account(company)
	found = []
	for doctype in INVOICE_DOCTYPES:
		dated = {"company": company, "posting_date": ["between", [first, last]]}
		fields = ["name", "posting_date", PARTY_FIELD[doctype], "tax_category", "base_grand_total"]
		purchase = doctype == "Purchase Invoice"
		if purchase:
			fields += ["base_net_total", "bill_date"]
		docs = frappe.get_all(
			doctype,
			filters={**dated, "docstatus": 1, "is_opening": ["!=", "Yes"]},
			fields=fields,
			order_by="posting_date, name",
		)
		charged = defaultdict(int)
		if purchase and docs:
			for row in frappe.get_all(
				"Purchase Taxes and Charges",
				filters={
					"parenttype": doctype,
					"parent": ["in", [d.name for d in docs]],
					"account_head": payable,
					"add_deduct_tax": "Deduct",
				},
				fields=["parent", "base_tax_amount_after_discount_amount"],
			):
				charged[row.parent] += cents(row.base_tax_amount_after_discount_amount)
		for doc in docs:
			vat = charged[doc.name]
			found.append(
				Document(
					doctype=doctype,
					name=doc.name,
					posting_date=getdate(doc.posting_date),
					party=doc.get(PARTY_FIELD[doctype]) or "",
					category=doc.tax_category or "",
					amount=cents(doc.base_grand_total) + vat,
					net=cents(doc.base_net_total) if purchase else cents(doc.base_grand_total),
					vat=vat,
					invoice_date=getdate(doc.bill_date) if purchase and doc.bill_date else None,
				)
			)
	found.sort(key=lambda d: (d.posting_date, d.doctype, d.name))
	return found


def payments(company: str, first: date, last: date) -> list[tuple[date, int, str, str]]:
	"""Payments of self-charged VAT posted from first to last: date, amount in cents, voucher type and voucher of
	every voucher other than a Purchase Invoice with a net debit on the payable account."""
	rows = frappe.db.sql(
		"""select posting_date, voucher_type, voucher_no, sum(debit - credit) as amount
		from `tabGL Entry`
		where company = %s and account = %s and is_cancelled = 0 and voucher_type != 'Purchase Invoice'
			and posting_date between %s and %s
		group by posting_date, voucher_type, voucher_no
		having sum(debit - credit) > 0
		order by posting_date, voucher_no""",
		(company, payable_account(company), first, last),
		as_dict=True,
	)
	return [(getdate(row.posting_date), cents(row.amount), row.voucher_type, row.voucher_no) for row in rows]
