"""Reads the books of a company for the VAT return of a period (return_form): the submitted invoices with their VAT
rows, the held drafts, the movements of the VAT accounts in the General Ledger and the settlement entries
(settlement.py). Opening invoices are left out. Settlement entries carry their period in the Journal Entry fields
FROM_FIELD and TO_FIELD (setup/vat.py) and are left out of the ledger check.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from malta_compliance.vat import return_form
from malta_compliance.vat.categories import ACCOUNTS, INPUT_ACCOUNTS, OUTPUT_ACCOUNTS
from malta_compliance.vat.return_form import money

SETTLEMENT_ACCOUNT = "2290"
FROM_FIELD = "mc_vat_from_date"
TO_FIELD = "mc_vat_to_date"
# VAT accounts cleared by a settlement; 3230 holds the VAT on private acquisitions and stays.
CLEARED = INPUT_ACCOUNTS + OUTPUT_ACCOUNTS
INVOICE_DOCTYPES = ("Sales Invoice", "Purchase Invoice")
PARTY_FIELD = {"Sales Invoice": "customer_name", "Purchase Invoice": "supplier_name"}
TAX_DOCTYPE = {"Sales Invoice": "Sales Taxes and Charges", "Purchase Invoice": "Purchase Taxes and Charges"}


@dataclass
class ReturnData:
	"""The return of a period and the state of the books behind it. expected: debit minus credit per VAT account of
	each counted invoice; differences: vouchers whose entries on the VAT accounts differ from the counted invoices,
	with the sum of the absolute differences; movements: debit minus credit per cleared account key in the period,
	without settlement entries."""

	company: str
	from_date: date
	to_date: date
	accounts: dict[str, str]
	result: return_form.Result
	drafts: list[str] = field(default_factory=list)
	ignored_rows: list[str] = field(default_factory=list)
	differences: list[tuple[str, str, int]] = field(default_factory=list)
	movements: dict[str, int] = field(default_factory=dict)
	settlements: list = field(default_factory=list)

	@property
	def label(self) -> str:
		return return_form.period_label(self.from_date, self.to_date)

	@property
	def books_payable(self) -> int:
		"""VAT payable by the movements of the cleared VAT accounts."""
		return -sum(self.movements.values())


def cents(value) -> int:
	return round(flt(value, 2) * 100)


def period(filters) -> tuple[date, date]:
	"""Period of the report filters year, period, from_date and to_date."""
	try:
		return return_form.period_dates(
			cint(filters.get("year")),
			filters.get("period"),
			getdate(filters.get("from_date")) if filters.get("from_date") else None,
			getdate(filters.get("to_date")) if filters.get("to_date") else None,
		)
	except ValueError as e:
		frappe.throw(str(e))


def vat_accounts(company: str) -> dict[str, str]:
	"""Names of the VAT accounts (keys of categories.ACCOUNTS) and of the settlement account (key "settlement")."""
	found = {}
	for key, number in {**ACCOUNTS, "settlement": SETTLEMENT_ACCOUNT}.items():
		name = frappe.db.get_value("Account", {"company": company, "account_number": number, "is_group": 0})
		if not name:
			frappe.throw(
				_(
					"Account {0} is missing in the company {1}; the VAT return needs the chart of the Malta app."
				).format(number, company)
			)
		found[key] = name
	return found


def has_settlement_fields() -> bool:
	meta = frappe.get_meta("Journal Entry")
	return bool(meta.has_field(FROM_FIELD) and meta.has_field(TO_FIELD))


def vat_return(
	company: str,
	from_date: date,
	to_date: date,
	adjustment_vat_department: int = 0,
	adjustment_registered_person: int = 0,
	credit_bf: int = 0,
) -> ReturnData:
	accounts = vat_accounts(company)
	key_of = {name: key for key, name in accounts.items() if key != "settlement"}
	invoices, expected, ignored = [], {}, []
	drafts = []
	for doctype in INVOICE_DOCTYPES:
		dated = {"company": company, "posting_date": ["between", [from_date, to_date]]}
		drafts += frappe.get_all(doctype, filters={**dated, "docstatus": 0}, pluck="name", order_by="name")
		docs = frappe.get_all(
			doctype,
			filters={**dated, "docstatus": 1, "is_opening": ["!=", "Yes"]},
			fields=["name", "posting_date", PARTY_FIELD[doctype], "tax_category", "base_net_total"],
			order_by="posting_date, name",
		)
		taxes = defaultdict(list)
		if docs:
			fields = ["parent", "account_head", "rate", "base_tax_amount_after_discount_amount"]
			if doctype == "Purchase Invoice":
				fields.append("add_deduct_tax")
			for row in frappe.get_all(
				TAX_DOCTYPE[doctype],
				filters={"parenttype": doctype, "parent": ["in", [d.name for d in docs]]},
				fields=fields,
				order_by="idx",
			):
				taxes[row.parent].append(row)
		for doc in docs:
			invoice, posted, rows_ignored = read_invoice(doctype, doc, taxes[doc.name], key_of)
			invoices.append(invoice)
			expected[(doctype, doc.name)] = posted
			ignored += rows_ignored
	result = return_form.compute(invoices, adjustment_vat_department, adjustment_registered_person, credit_bf)
	counted = {(i.doctype, i.name) for i in result.counted}
	moved = ledger(company, from_date, to_date, accounts)
	data = ReturnData(company, from_date, to_date, accounts, result, drafts, ignored)
	data.differences = differences(moved, {k: v for k, v in expected.items() if k in counted})
	cleared = {accounts[key]: key for key in CLEARED}
	movements = defaultdict(int)
	for by_account in moved.values():
		for account, amount in by_account.items():
			if account in cleared:
				movements[cleared[account]] += amount
	data.movements = {key: movements[key] for key in CLEARED}
	data.settlements = settlements(company, accounts, from_date, to_date)
	return data


def read_invoice(doctype: str, doc, rows, key_of: dict[str, str]):
	"""The invoice for return_form, the entries its VAT rows post (debit minus credit per account) and the rows the
	return does not count."""
	sale = doctype == "Sales Invoice"
	output = input_vat = 0
	rates, posted, ignored = [], defaultdict(int), []
	for row in rows:
		amount = cents(row.base_tax_amount_after_discount_amount)
		key = key_of.get(row.account_head)
		if key is None:
			if amount:
				ignored.append(f"{doc.name}: {row.account_head} {money(amount)}")
			continue
		rates.append(flt(row.rate))
		deduct = not sale and row.add_deduct_tax == "Deduct"
		if key in OUTPUT_ACCOUNTS and (sale or deduct):
			output += amount
		elif key in INPUT_ACCOUNTS and not sale and not deduct:
			input_vat += amount
		elif not (key == "private_vat" and not sale and not deduct):
			if amount:
				ignored.append(f"{doc.name}: {row.account_head} {money(amount)}")
			continue
		posted[row.account_head] += -amount if (sale or deduct) else amount
	invoice = return_form.Invoice(
		doctype=doctype,
		name=doc.name,
		posting_date=doc.posting_date,
		party=doc.get(PARTY_FIELD[doctype]) or "",
		category=doc.tax_category or "",
		base=cents(doc.base_net_total),
		output_vat=output,
		input_vat=input_vat,
		rates=tuple(rates),
	)
	return invoice, dict(posted), ignored


def settlement_entries(company: str, from_date: date, to_date: date) -> list[str]:
	"""Submitted settlement entries posted in the period."""
	if not has_settlement_fields():
		return []
	return frappe.get_all(
		"Journal Entry",
		filters=[
			["company", "=", company],
			["docstatus", "=", 1],
			[FROM_FIELD, "is", "set"],
			["posting_date", "between", [from_date, to_date]],
		],
		pluck="name",
	)


def ledger(company: str, from_date: date, to_date: date, accounts: dict[str, str]):
	"""Debit minus credit per voucher and VAT account in the period, without settlement entries."""
	exclude = set(settlement_entries(company, from_date, to_date))
	vat_names = [name for key, name in accounts.items() if key != "settlement"]
	moved = defaultdict(lambda: defaultdict(int))
	for row in frappe.get_all(
		"GL Entry",
		filters={
			"company": company,
			"is_cancelled": 0,
			"posting_date": ["between", [from_date, to_date]],
			"account": ["in", vat_names],
		},
		fields=["voucher_type", "voucher_no", "account", "debit", "credit"],
	):
		if row.voucher_type == "Journal Entry" and row.voucher_no in exclude:
			continue
		moved[(row.voucher_type, row.voucher_no)][row.account] += cents(row.debit) - cents(row.credit)
	return moved


def differences(moved, expected) -> list[tuple[str, str, int]]:
	found = []
	for voucher in sorted(set(moved) | set(expected), key=lambda v: (v[0], v[1])):
		posted, wanted = moved.get(voucher, {}), expected.get(voucher, {})
		difference = sum(abs(posted.get(a, 0) - wanted.get(a, 0)) for a in set(posted) | set(wanted))
		if difference:
			found.append((voucher[0], voucher[1], difference))
	return found


def settlements(company: str, accounts: dict[str, str], from_date: date, to_date: date) -> list:
	"""Settlement entries, draft or submitted, whose period overlaps the given one, with the VAT payable they
	clear (cleared) and the amount they book on the settlement account (filed), both in cents."""
	if not has_settlement_fields():
		return []
	entries = frappe.get_all(
		"Journal Entry",
		filters=[
			["company", "=", company],
			["docstatus", "<", 2],
			[FROM_FIELD, "<=", to_date],
			[TO_FIELD, ">=", from_date],
		],
		fields=["name", "docstatus", "posting_date", FROM_FIELD, TO_FIELD],
		order_by=f"{FROM_FIELD}, name",
	)
	if not entries:
		return []
	cleared_names = {accounts[key] for key in CLEARED}
	rows = defaultdict(list)
	for row in frappe.get_all(
		"Journal Entry Account",
		filters={"parenttype": "Journal Entry", "parent": ["in", [e.name for e in entries]]},
		fields=["parent", "account", "debit", "credit"],
	):
		rows[row.parent].append(row)
	for entry in entries:
		entry.from_date = getdate(entry.get(FROM_FIELD))
		entry.to_date = getdate(entry.get(TO_FIELD))
		entry.cleared = sum(
			cents(r.debit) - cents(r.credit) for r in rows[entry.name] if r.account in cleared_names
		)
		entry.filed = sum(
			cents(r.credit) - cents(r.debit) for r in rows[entry.name] if r.account == accounts["settlement"]
		)
	return entries
