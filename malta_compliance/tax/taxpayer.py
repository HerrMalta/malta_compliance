"""Figures of a year built from a Malta Taxpayer record where no Malta Tax Year record of the year exists, and the
kind of each payment booked on 3210 and 3220 (docs/income-tax.md). A built year is a Malta Tax Year that is not
saved: a year with a filed return takes its profits and tax from the return, any other year the profit of the
listed companies from the books. The net profits of a filed return are the Class 2 base of the following year.
Built years are cached for the request; clear_cache() starts afresh.
"""

from datetime import date
from decimal import Decimal

import frappe
from frappe.utils import getdate

from malta_compliance.tax import books, income_tax, provisional_tax, rules
from malta_compliance.tax import year as tax_year

DOCTYPE = "Malta Taxpayer"
PERSONS = ((tax_year.SELF, "self", "self_net_profit"), (tax_year.SPOUSE, "spouse", "spouse_net_profit"))


def clear_cache() -> None:
	frappe.local.malta_built_years = {}


def for_company(company: str) -> str | None:
	"""Name of the Malta Taxpayer listing the company, or None."""
	return frappe.db.get_value(
		"Malta Tax Year Company", {"parenttype": DOCTYPE, "company": company}, "parent"
	)


def first_year(master) -> int | None:
	"""First basis year of the record: the earliest start of a self-occupation or filed return."""
	years = [
		getdate(master.get(f"{prefix}_occupied_from")).year
		for _p, prefix, _f in PERSONS
		if master.get(f"{prefix}_occupied_from")
	]
	years += [int(row.basis_year) for row in master.returns]
	return min(years) if years else None


def filed_return(master, year: int):
	"""The row of the filed return of the basis year, or None."""
	return next((row for row in master.returns if int(row.basis_year) == year), None)


def built_year(taxpayer: str, year: int):
	"""The Malta Tax Year of the taxpayer and basis year built from its Malta Taxpayer record, not saved; None without
	that record or before its first year."""
	cache = getattr(frappe.local, "malta_built_years", None)
	if cache is None:
		clear_cache()
		cache = frappe.local.malta_built_years
	key = (taxpayer, year)
	if key not in cache:
		cache[key] = None
		if frappe.db.exists(DOCTYPE, taxpayer):
			master = frappe.get_doc(DOCTYPE, taxpayer)
			master.check_permission("read")
			start = first_year(master)
			if start is not None and year >= start:
				cache[key] = build(master, year)
	return cache[key]


def build(master, year: int):
	doc = frappe.new_doc("Malta Tax Year")
	doc.update(
		{
			"taxpayer": master.name,
			"basis_year": str(year),
			"year_of_assessment": str(year + 1),
			"status": master.status,
			"children": master.children,
			"child_tables": master.child_tables,
		}
	)
	married = master.status == income_tax.MARRIED
	filed, previous = filed_return(master, year), filed_return(master, year - 1)
	if filed:
		doc.update(
			{"filed": 1, "filed_tax": filed.tax_charged, "filed_chargeable_income": filed.chargeable_income}
		)
	for person, prefix, profit_field in PERSONS:
		if person == tax_year.SPOUSE and not married:
			continue
		born = master.get(f"{prefix}_year_of_birth")
		start = (
			getdate(master.get(f"{prefix}_occupied_from")) if master.get(f"{prefix}_occupied_from") else None
		)
		end = (
			getdate(master.get(f"{prefix}_occupied_until"))
			if master.get(f"{prefix}_occupied_until")
			else None
		)
		outside = bool(start and start.year > year) or bool(end and end.year < year)
		doc.set(f"{prefix}_born_before_1962", 1 if born and int(born) < 1962 else 0)
		doc.set(f"{prefix}_no_class2", 1 if master.get(f"{prefix}_no_class2") or outside else 0)
		doc.set(f"{prefix}_first_year", 1 if start and start.year == year else 0)
		doc.set(f"{prefix}_active_from", start if start and start.year == year else None)
		doc.set(f"{prefix}_active_to", end if end and end.year == year else None)
		if previous and (previous.get(profit_field) or start):
			doc.set(f"{prefix}_class2_base_entered", 1)
			doc.set(f"{prefix}_class2_base", previous.get(profit_field) or 0)
		if filed and filed.get(profit_field):
			doc.append(
				"items",
				{
					"kind": tax_year.TRADE,
					"person": person,
					"description": "Net profit as filed",
					"amount": filed.get(profit_field),
				},
			)
	if not filed:
		for row in master.companies:
			if married or row.person == tax_year.SELF:
				doc.append("companies", {"company": row.company, "person": row.person})
	frappe.local.malta_built_years[(master.name, year)] = doc
	persons = {row.company: row.person for row in master.companies}
	rows = book_payments(persons, year)
	for row in rows:
		doc.append("payments", row)
	classify(doc, doc.payments)
	if filed and filed.get("provisional_tax_paid"):
		add_filed_provisional_tax(doc, Decimal(str(filed.provisional_tax_paid)))
	return doc


def add_filed_provisional_tax(doc, total: Decimal) -> None:
	"""Provisional tax of return box 36 for a year without provisional tax in the books: one row per instalment
	due date in the order of the instalments, the rest on the last one. The return does not state the dates."""
	if any(p.kind == tax_year.PROVISIONAL_TAX for p in doc.payments):
		return
	dues = instalments(doc)
	last = dues[-1].due if dues else date(tax_year.basis_year(doc), 12, 31)
	rest = total
	for instalment in dues:
		part = min(rest, Decimal(instalment.amount))
		if part > 0:
			doc.append("payments", filed_payment(instalment.due, part))
			rest -= part
	if rest > 0:
		doc.append("payments", filed_payment(last, rest))


def filed_payment(on: date, amount: Decimal) -> dict:
	return {
		"posting_date": on,
		"kind": tax_year.PROVISIONAL_TAX,
		"person": tax_year.SELF,
		"amount": amount,
		"remarks": "Return box 36 as filed; date assumed",
	}


def book_payments(persons: dict[str, str], year: int) -> list[dict]:
	"""Payments booked in the year on 3210 and 3220 of the companies, unless a saved Malta Tax Year lists them."""
	listed = {
		(row.voucher_no, row.account)
		for row in frappe.get_all(
			"Malta Tax Year Payment", filters={"voucher_no": ["is", "set"]}, fields=["voucher_no", "account"]
		)
	}
	rows = []
	for payment in books.payments(list(persons), date(year, 1, 1), date(year, 12, 31)):
		if (payment.voucher_no, payment.account) in listed:
			continue
		rows.append(
			{
				"posting_date": payment.posting_date,
				"person": persons[payment.company],
				"amount": payment.amount,
				"account": payment.account,
				"voucher_type": payment.voucher_type,
				"voucher_no": payment.voucher_no,
				"remarks": payment.remarks,
			}
		)
	return rows


def instalment_amounts(doc) -> list[int]:
	"""Amounts of instalments(doc)."""
	return [row.amount for row in instalments(doc)]


def instalments(doc) -> list:
	"""The three provisional tax instalments of a record, without a reduction form; empty when the benchmark cannot
	be computed."""
	if doc is None:
		return []
	try:
		benchmark, _origin = tax_year.pt_benchmark(doc)
		return provisional_tax.instalments(benchmark, tax_year.basis_year(doc), None, None, lambda until: 0)
	except rules.NotCovered, frappe.ValidationError:
		return []


def classify(doc, payments) -> int:
	"""Sets the kind of each payment row without one and returns their number. A payment on 3220 is a Class 2
	contribution of the year. A payment on 3210 is provisional tax of the year when it equals an instalment of the
	year not matched yet, provisional tax of the preceding year when it equals an instalment of that year, and
	otherwise the settlement of the preceding year."""
	year = tax_year.basis_year(doc)
	current = instalment_amounts(doc)
	for row in payments:
		match = next((a for a in current if abs(Decimal(str(row.amount)) - a) < 1), None)
		if row.kind == tax_year.PROVISIONAL_TAX and match is not None:
			current.remove(match)
	preceding = None
	set_kinds = 0
	for row in sorted(payments, key=lambda p: getdate(p.posting_date)):
		if row.kind or not row.account:
			continue
		number = frappe.get_cached_value("Account", row.account, "account_number")
		if number == books.CLASS2_PAYMENTS:
			row.kind = tax_year.CLASS2
		elif number == books.INCOME_TAX_PAYMENTS:
			if preceding is None:
				preceding = instalment_amounts(tax_year.find(doc.taxpayer, year - 1))
			amount = Decimal(str(row.amount))
			match = next((a for a in current if abs(amount - a) < 1), None)
			if match is not None:
				current.remove(match)
				row.kind = tax_year.PROVISIONAL_TAX
			else:
				match = next((a for a in preceding if abs(amount - a) < 1), None)
				if match is not None:
					preceding.remove(match)
					row.kind = tax_year.PROVISIONAL_TAX_PRECEDING
				else:
					row.kind = tax_year.SETTLEMENT_PRECEDING
		else:
			continue
		set_kinds += 1
	return set_kinds
