"""Declaration of a registration under Article 11 for a calendar year in the four boxes of its form, computed from
the submitted invoices by their tax categories, with the turnover against the limit of a small enterprise and the
goods acquired from other Member States against the acquisitions threshold (README, "VAT registrations under
Articles 11 and 12"). The note under the report lists the registrations of the company, the due date and the checks
of the books.
"""

from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, flt

from malta_compliance.vat import declaration, declaration_books, registration, rules
from malta_compliance.vat.categories import ARTICLE_11_BOXES
from malta_compliance.vat.return_form import money

# Names listed in a note before the rest is counted.
MAX_NAMES = 10
# Last year whose limits are in Maltese liri.
LAST_LIRI_YEAR = 2007


def execute(filters=None):
	filters = frappe._dict(filters or {})
	for doctype in ("Sales Invoice", "Purchase Invoice", registration.DOCTYPE):
		frappe.has_permission(doctype, "read", throw=True)
	year = cint(filters.year)
	record = registration.get(filters.company)
	if record is None:
		frappe.throw(
			_("No Malta VAT Registration lists the company {0}. Create one under Malta VAT Registration.").format(
				filters.company
			)
		)
	if year < 1000:
		frappe.throw(_("Year {0} is not a calendar year with four digits.").format(filters.year))
	first, last = date(year, 1, 1), date(year, 12, 31)
	documents = declaration_books.documents(filters.company, date(year - 1, 1, 1), last)
	result = declaration.declaration([d for d in documents if d.posting_date.year == year])
	try:
		tests = declaration.limit_tests(documents, year, record.activity, registration.started(record))
	except rules.NotCovered as e:
		frappe.throw(str(e), title=_("Year not covered by the rule register"))
	acquired = declaration.acquisitions(documents, year)
	drafts = declaration_books.drafts(filters.company, first, last)
	text = notes(filters.company, year, record, documents, result, tests, acquired, drafts)
	return columns(filters), rows(year, result, tests, acquired, filters), "<br>".join(text)


def columns(filters) -> list[dict]:
	result = [
		{"fieldname": "line", "label": _("Line"), "fieldtype": "Data", "width": 460},
		{"fieldname": "box", "label": _("Box"), "fieldtype": "Data", "width": 60},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "limit", "label": _("Limit"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 200},
	]
	if filters.show_invoices:
		result += [
			{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
			{
				"fieldname": "voucher_no",
				"label": _("Invoice"),
				"fieldtype": "Dynamic Link",
				"options": "voucher_type",
				"width": 180,
			},
		]
	return result


def section(label: str) -> dict:
	return {"key": "", "line": label, "kind": "section", "indent": 0, "bold": 1}


def test_row(key: str, test: declaration.LimitTest) -> dict:
	if test.exceeded_on:
		status = _("exceeded on {0}").format(frappe.format(test.exceeded_on, {"fieldtype": "Date"}))
	else:
		status = _("exceeded") if test.exceeded else _("within the limit")
	return {
		"key": key,
		"line": _("{0}, preceding year").format(test.label) if test.preceding else test.label,
		"kind": "test",
		"indent": 1,
		"bold": 0,
		"amount": flt(test.value / 100, 2),
		"limit": None if test.limit is None else flt(test.limit / 100, 2),
		"status": status,
		"exceeded": 1 if test.exceeded else 0,
	}


def rows(year: int, result: declaration.Declaration, tests, acquired, filters) -> list[dict]:
	"""The four boxes, with their invoices for show_invoices, then one row per limit test. Rows carry a key for
	scripts reading the report: box_1 to box_4, turnover_<last day of the period> and acquisitions."""
	out = [section(_("Statement of sales and purchases {0}").format(year))]
	for box, label in ARTICLE_11_BOXES:
		out.append(
			{
				"key": f"box_{box}",
				"line": _(label),
				"box": box,
				"kind": "box",
				"indent": 1,
				"bold": 0,
				"amount": flt(result.boxes[box] / 100, 2),
			}
		)
		if filters.show_invoices:
			for document in result.entries.get(box, []):
				out.append(
					{
						"key": "",
						"line": document.party,
						"kind": "invoice",
						"indent": 2,
						"bold": 0,
						"amount": flt(document.amount / 100, 2),
						"posting_date": document.posting_date,
						"voucher_type": document.doctype,
						"voucher_no": document.name,
					}
				)
	out.append(section(_("Turnover against the limit of a small enterprise")))
	out += [test_row(f"turnover_{test.last.isoformat()}", test) for test in tests]
	if acquired:
		out.append(section(_("Goods acquired from other Member States")))
		out.append(test_row("acquisitions", acquired))
	return out


def listed(names: list[str]) -> str:
	text = ", ".join(names[:MAX_NAMES])
	if len(names) > MAX_NAMES:
		text += " " + _("and {0} more").format(len(names) - MAX_NAMES)
	return text


def notes(company: str, year: int, record, documents, result, tests, acquired, drafts) -> list[str]:
	first, last = date(year, 1, 1), date(year, 12, 31)
	counted = sum(len(entries) for entries in result.entries.values())
	lines = [
		_(
			"{0}: submitted Sales and Purchase Invoices of {1} dated in the year, without opening invoices; {2} in "
			"the boxes, {3} outside the declaration. The declaration is due on {4}."
		).format(
			year,
			company,
			counted,
			len(result.outside),
			frappe.format(rules.declaration_due(year), {"fieldtype": "Date"}),
		)
	]
	lines += registration_notes(record, first, last)
	if result.unknown:
		lines.append(
			_("Not in the declaration, without a tax category of an Article 11 company: {0}.").format(
				listed([d.name for d in result.unknown])
			)
		)
	if drafts:
		lines.append(
			_("Drafts dated in the year, not in the declaration until submitted: {0}.").format(listed(drafts))
		)
	lines += limit_notes(year, record, tests)
	if acquired:
		lines += acquisition_notes(record, acquired)
	services = [
		d
		for d in declaration.eu_customer_services(documents, year)
		if not registration.row_on(record, registration.ARTICLE_12, d.posting_date)
	]
	if services:
		lines.append(
			_(
				"A service whose VAT a customer in another Member State pays requires a registration under Article "
				"12 from {0} (VAT Act art. 12(3a)); the Malta VAT Registration lists none on the date of: {1}."
			).format(rules.ARTICLE_12_SERVICES_SUPPLIED_FROM.isoformat(), listed([d.name for d in services]))
		)
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


def registration_notes(record, first: date, last: date) -> list[str]:
	lines = []
	described = [
		text
		for text in (
			registration.described(record, article)
			for article in (registration.ARTICLE_11, registration.ARTICLE_10, registration.ARTICLE_12)
		)
		if text
	]
	lines.append(_("Malta VAT Registration: {0}.").format("; ".join(described)))
	if not registration.overlaps(record, registration.ARTICLE_11, first, last):
		lines.append(_("The record lists no registration under Article 11 in {0}.").format(first.year))
	if registration.overlaps(record, registration.ARTICLE_10, first, last):
		lines.append(
			_(
				"The record lists a registration under Article 10 in {0}; the report VAT Return Malta computes the "
				"returns of its days."
			).format(first.year)
		)
	return lines


def limit_notes(year: int, record, tests) -> list[str]:
	if not tests:
		return [_("No period of the year is tested against the turnover limit: the activity started within it.")]
	sources = "; ".join(dict.fromkeys(test.source for test in tests))
	current = tests[0]
	if current.first == date(year, 1, 1) and current.last == date(year, 12, 31):
		lines = [
			_(
				"Turnover limit: the supplies taking place in Malta in the calendar year against {0}, without "
				"disposals of capital assets ({1}). A registration under Article 11 ends when the limit is exceeded: "
				"application within 15 days, registration under Article 10 from the first day of the following month "
				"(art. 11(5) and (7))."
			).format(money(current.limit), sources)
		]
	else:
		lines = [
			_(
				'Turnover limit of the activity "{0}": on the first day of each calendar quarter, the turnover of '
				"the twelve months before it against the limit of that day, in proportion for a shorter period; "
				"supplies outside Malta count, disposals of capital assets do not ({1})."
			).format(record.activity, sources)
		]
	if year <= LAST_LIRI_YEAR:
		lines.append(
			_("The limits of {0} are in Maltese liri, converted at {1} liri per euro.").format(
				year, rules.MTL_PER_EUR
			)
		)
	if rules.NO_REGISTRATION_YEARS[0] <= year <= rules.NO_REGISTRATION_YEARS[1]:
		lines.append(
			_(
				"In {0} a person with a turnover of at most {1} in the calendar year was not registered under "
				"Article 11 and issued no fiscal receipts ({2})."
			).format(year, money(rules.NO_REGISTRATION_LIMIT * 100), rules.NO_REGISTRATION_SOURCE)
		)
	return lines


def acquisition_notes(record, acquired: declaration.LimitTest) -> list[str]:
	lines = [
		_(
			"Goods acquired from other Member States against the acquisitions threshold of {0} ({1}): a purchase "
			"under Article 12 counts with its net total, any other as booked, with the VAT of the other Member State."
		).format(money(acquired.limit), acquired.source)
	]
	if acquired.exceeded_on and not registration.row_on(
		record, registration.ARTICLE_12, acquired.exceeded_on
	):
		lines.append(
			_(
				"The threshold was exceeded on {0}; the Malta VAT Registration lists no registration under Article "
				"12 on that day (art. 12(1))."
			).format(frappe.format(acquired.exceeded_on, {"fieldtype": "Date"}))
		)
	return lines
