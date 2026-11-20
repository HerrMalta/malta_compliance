"""VAT self-charged under Article 12 in a calendar year: one row per purchase with a tax category of Article 12, as
in the notice of payment, with its due date and the payments applied to it, and the figures of the annual
declaration (README, "VAT registrations under Articles 11 and 12"). Payments are the debits on 2220 Output VAT
Reverse Charge from vouchers other than Purchase Invoices, posted from the first day of the registration under
Article 12 and applied to the notices in the order of their due dates; none is read without such a registration.
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from malta_compliance.vat import article12, declaration_books, registration, rules
from malta_compliance.vat.categories import ARTICLE_12_BY_TITLE
from malta_compliance.vat.return_form import money

# Names listed in a note before the rest is counted.
MAX_NAMES = 10
AMOUNTS = ("value", "vat", "paid", "open")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	for doctype in ("Purchase Invoice", "GL Entry", registration.DOCTYPE):
		frappe.has_permission(doctype, "read", throw=True)
	year = cint(filters.year)
	as_of = getdate(filters.as_of or nowdate())
	record = registration.get(filters.company)
	if record is None:
		frappe.throw(
			_("No Malta VAT Registration lists the company {0}. Create one under Malta VAT Registration.").format(
				filters.company
			)
		)
	if year < 1000:
		frappe.throw(_("Year {0} is not a calendar year with four digits.").format(filters.year))
	first = first_day(record)
	documents = declaration_books.documents(filters.company, first, max(date(year, 12, 31), as_of))
	try:
		entries = article12.notices(documents)
	except rules.NotCovered as e:
		frappe.throw(str(e), title=_("Purchase not covered by the rule register"))
	registered = registration.rows(record, registration.ARTICLE_12)
	payments = declaration_books.payments(filters.company, first, as_of) if registered else []
	settled, excess = article12.settle(entries, [(paid_on, amount) for paid_on, amount, *_ in payments])
	of_year = [s for s in settled if s.notice.received.year == year]
	drafts = [
		name
		for name in declaration_books.drafts(filters.company, date(year, 1, 1), date(year, 12, 31))
		if frappe.db.get_value("Purchase Invoice", name, "tax_category") in ARTICLE_12_BY_TITLE
	]
	text = notes(filters.company, year, as_of, first, record, of_year, settled, payments, excess, drafts)
	return columns(), rows(year, of_year, article12.annual(entries, year)), "<br>".join(text)


def first_day(record) -> date:
	"""First day of the earliest registration under Article 12, not before the first day Article 12 applied; that
	day where the record lists no registration under Article 12 or one without a first day."""
	firsts = [registration.bounds(row)[0] for row in registration.rows(record, registration.ARTICLE_12)]
	return max(min(firsts, default=date.min), rules.ARTICLE_12_GOODS_FROM)


def columns() -> list[dict]:
	return [
		{"fieldname": "line", "label": _("Supplier / Line"), "fieldtype": "Data", "width": 340},
		{
			"fieldname": "voucher_no",
			"label": _("Invoice"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 170,
		},
		{"fieldname": "invoice_date", "label": _("Invoice Date"), "fieldtype": "Date", "width": 105},
		{"fieldname": "received", "label": _("Acquired / Received"), "fieldtype": "Date", "width": 105},
		{"fieldname": "supply", "label": _("Type"), "fieldtype": "Data", "width": 80},
		{"fieldname": "from_eu", "label": _("From EU"), "fieldtype": "Data", "width": 75},
		{"fieldname": "value", "label": _("Value"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "vat", "label": _("VAT"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "due", "label": _("Due"), "fieldtype": "Date", "width": 105},
		{"fieldname": "paid", "label": _("Paid"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "paid_on", "label": _("Last Payment"), "fieldtype": "Date", "width": 105},
		{"fieldname": "open", "label": _("Open"), "fieldtype": "Currency", "width": 110},
	]


def section(label: str) -> dict:
	return {"key": "", "line": label, "kind": "section", "indent": 0, "bold": 1}


def rows(year: int, of_year: list[article12.Settled], annual: dict[str, list[int]]) -> list[dict]:
	"""The notices of the year by due date with their total, then the lines of the annual declaration with their
	total. Rows carry a key for scripts reading the report: notice, notices_total, the keys of
	article12.ANNUAL_LINES and annual_total."""
	out = [section(_("Notices of payment {0}").format(year))]
	for item in of_year:
		entry = item.notice
		out.append(
			{
				"key": "notice",
				"line": entry.document.party,
				"kind": "notice",
				"indent": 1,
				"bold": 0,
				"voucher_type": entry.document.doctype,
				"voucher_no": entry.document.name,
				"invoice_date": entry.invoice_date,
				"received": entry.received,
				"supply": _(entry.kind),
				"from_eu": _("Yes") if entry.eu else _("No"),
				"value": flt(entry.value / 100, 2),
				"vat": flt(entry.vat / 100, 2),
				"due": entry.due,
				"paid": flt(item.paid / 100, 2),
				"paid_on": item.paid_on,
				"open": flt(item.open / 100, 2),
			}
		)
	notice_rows = [row for row in out if row["key"] == "notice"]
	out.append(
		{
			"key": "notices_total",
			"line": _("Total"),
			"kind": "total",
			"indent": 0,
			"bold": 1,
			**{name: flt(sum(row[name] for row in notice_rows), 2) for name in AMOUNTS},
		}
	)
	out.append(
		section(
			_("Annual declaration {0}, due on {1}").format(
				year, frappe.format(rules.declaration_due(year), {"fieldtype": "Date"})
			)
		)
	)
	for key, label in article12.ANNUAL_LINES:
		value, vat = annual[key]
		out.append(
			{
				"key": key,
				"line": _(label),
				"kind": "annual",
				"indent": 1,
				"bold": 0,
				"value": flt(value / 100, 2),
				"vat": flt(vat / 100, 2),
			}
		)
	out.append(
		{
			"key": "annual_total",
			"line": _("Total"),
			"kind": "total",
			"indent": 0,
			"bold": 1,
			"value": flt(sum(value for value, _vat in annual.values()) / 100, 2),
			"vat": flt(sum(vat for _value, vat in annual.values()) / 100, 2),
		}
	)
	return out


def shown(value: date) -> str:
	return frappe.format(value, {"fieldtype": "Date"})


def listed(names: list[str]) -> str:
	text = ", ".join(names[:MAX_NAMES])
	if len(names) > MAX_NAMES:
		text += " " + _("and {0} more").format(len(names) - MAX_NAMES)
	return text


def notes(
	company: str, year: int, as_of: date, first: date, record, of_year, settled, payments, excess, drafts
) -> list[str]:
	lines = [
		_(
			"{0}: submitted Purchase Invoices of {1} with a tax category of Article 12, acquired or received in the "
			"year; {2} in the notices. The VAT of a notice is the VAT as booked on its invoice."
		).format(year, company, len(of_year))
	]
	described = registration.described(record, registration.ARTICLE_12)
	lines.append(
		_("Malta VAT Registration: {0}.").format(described)
		if described
		else _("The Malta VAT Registration lists no registration under Article 12.")
	)
	unregistered = [
		s.notice.document.name
		for s in of_year
		if not registration.row_on(record, registration.ARTICLE_12, s.notice.received)
	]
	if described and unregistered:
		lines.append(
			_("Dated on a day without a registration under Article 12: {0}.").format(listed(unregistered))
		)
	lines.append(
		_(
			"Due dates: goods on the 15th day of the month after the month in which the VAT becomes chargeable "
			"(art. 21(2); Fourth Schedule, item 6), services on the 15th day of the second month after the month of "
			"the invoice or, where earlier, of the supply (art. 21(3))."
		)
	)
	if described:
		lines.append(
			_(
				"Payments: debits on {0} from vouchers other than Purchase Invoices, posted from {1} to {2} and "
				"applied to the notices in the order of their due dates: {3}."
			).format(
				declaration_books.payable_account(company),
				shown(first),
				shown(as_of),
				money(sum(amount for _paid_on, amount, *_ in payments)),
			)
		)
	if excess:
		lines.append(_("Payments above the VAT of the notices up to {0}: {1}.").format(shown(as_of), money(excess)))
	overdue = sum(s.open for s in settled if s.notice.due < as_of)
	if overdue:
		line = _("Overdue on {0}, with the notices of earlier years: {1}.").format(shown(as_of), money(overdue))
		try:
			rate = rules.interest(as_of)
			line += " " + _(
				"VAT unpaid after its due date bears interest of {0}% for every month or part of a month ({1}); "
				"the report computes no interest."
			).format(rate.percent, rate.source)
		except rules.NotCovered:
			pass
		lines.append(line)
	if drafts:
		lines.append(_("Drafts dated in the year, not in the notices until submitted: {0}.").format(listed(drafts)))
	try:
		penalty = rules.late_declaration(rules.declaration_due(year))
		lines.append(
			_(
				"A declaration furnished late: {0} for every month or part of a month, at most {1} ({2})."
			).format(money(penalty.per_month * 100), money(penalty.maximum * 100), penalty.source)
		)
	except rules.NotCovered:
		pass
	warning = rules.review_warning(year)
	if warning:
		lines.append(warning)
	return lines
