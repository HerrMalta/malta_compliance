"""Settlement entry of a VAT return period: a draft Journal Entry dated the last day of the period that clears the
period's movements of the VAT accounts 1310, 1320, 2210 and 2220 against 2290 VAT Settlement at the VAT payable as
filed, with a difference of at most return_form.MAX_ROUNDING cents on the Round Off account of the company. 3230
holds the VAT on private acquisitions and is not cleared. The entry carries its period in the fields
books.FROM_FIELD and books.TO_FIELD; a refund or a payment is booked on 2290 from the bank statement.
"""

import frappe
from frappe import _
from frappe.utils import flt

from malta_compliance.vat import books, return_form
from malta_compliance.vat.return_form import money

MANAGER_ROLES = ("Accounts Manager", "System Manager")


@frappe.whitelist()
def create_settlement(filters, filed_payable) -> str:
	"""Creates the draft settlement entry of the period of the report filters (company, year, period, from_date,
	to_date) for the VAT payable as filed in box 42, negative for an excess credit; returns its name."""
	frappe.only_for(MANAGER_ROLES)
	frappe.has_permission("Journal Entry", "create", throw=True)
	if not books.has_settlement_fields():
		frappe.throw(
			_("The Journal Entry fields of the VAT settlement are missing; run the migration of the site.")
		)
	filters = frappe._dict(frappe.parse_json(filters) if isinstance(filters, str) else filters)
	from_date, to_date = books.period(filters)
	data = books.vat_return(filters.company, from_date, to_date)
	problems = blocking(data)
	if problems:
		frappe.throw("<br>".join(problems), title=_("VAT period {0} not settled").format(data.label))
	filed = books.cents(flt(filed_payable))
	try:
		amounts = return_form.settlement(data.movements, filed)
	except ValueError as e:
		frappe.throw(str(e), title=_("VAT period {0} not settled").format(data.label))
	doc = entry(data, amounts, filed)
	doc.insert()
	return doc.name


def blocking(data: books.ReturnData) -> list[str]:
	"""Reasons why the books of the period cannot be settled yet."""
	problems = []
	for e in data.settlements:
		problems.append(
			_("The period {0} to {1} is settled by {2}.").format(e.from_date, e.to_date, e.name)
			if e.docstatus == 1
			else _("The draft {0} settles the period {1} to {2}; submit or delete it.").format(
				e.name, e.from_date, e.to_date
			)
		)
	if data.drafts:
		problems.append(_("Drafts dated in the period: {0}.").format(", ".join(data.drafts)))
	if data.result.unknown:
		problems.append(
			_("Invoices without a VAT category of the return: {0}.").format(
				", ".join(i.name for i in data.result.unknown)
			)
		)
	if data.differences:
		problems.append(
			_("Entries on the VAT accounts that the counted invoices do not explain: {0}.").format(
				", ".join(name for _doctype, name, _amount in data.differences)
			)
		)
	box42 = data.result.tax("42")
	if not problems and data.books_payable != box42:
		problems.append(
			_("The VAT accounts give a VAT payable of {0}, the invoices {1}.").format(
				money(data.books_payable), money(box42)
			)
		)
	if not problems and not any(data.movements.values()):
		problems.append(_("The VAT accounts did not move in the period; there is nothing to settle."))
	return problems


def entry(data: books.ReturnData, amounts: return_form.Settlement, filed: int):
	company = frappe.get_cached_doc("Company", data.company)
	if amounts.rounding and not company.round_off_account:
		frappe.throw(_("The company {0} has no Round Off Account.").format(data.company))
	rows = [line(data.accounts[key], amount) for key, amount in amounts.accounts.items()]
	if amounts.settlement:
		rows.append(line(data.accounts["settlement"], amounts.settlement))
	if amounts.rounding:
		rows.append(
			line(
				company.round_off_account,
				amounts.rounding,
				company.round_off_cost_center or company.cost_center,
			)
		)
	remark = _(
		"VAT settlement {0} ({1} to {2}), report VAT Return Malta: VAT payable as filed {3} on {4}, VAT payable of "
		"the invoices {5}"
	).format(
		data.label,
		data.from_date,
		data.to_date,
		money(filed),
		data.accounts["settlement"],
		money(amounts.computed),
	)
	if amounts.rounding:
		remark += _(", difference {0} on {1}").format(money(amounts.rounding), company.round_off_account)
	return frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"title": _("VAT settlement {0}").format(data.label),
			"company": data.company,
			"posting_date": data.to_date,
			"user_remark": remark + ".",
			books.FROM_FIELD: data.from_date,
			books.TO_FIELD: data.to_date,
			"accounts": rows,
		}
	)


def line(account: str, amount: int, cost_center: str | None = None) -> dict:
	"""A Journal Entry row for an amount in cents, debit when positive."""
	row = {
		"account": account,
		"debit_in_account_currency": flt(amount / 100, 2) if amount > 0 else 0,
		"credit_in_account_currency": flt(-amount / 100, 2) if amount < 0 else 0,
	}
	if cost_center:
		row["cost_center"] = cost_center
	return row
