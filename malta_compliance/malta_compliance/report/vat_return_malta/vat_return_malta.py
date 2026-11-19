"""VAT return of a period in the lines of the tax accountant's worksheet and the boxes of the return form, computed
from the submitted invoices by their tax categories (README, "VAT return"). The note under the report lists the
checks of the books: invoices outside the return, held drafts, entries on the VAT accounts not explained by the
counted invoices, and the settlement entry of the period.
"""

import frappe
from frappe import _
from frappe.utils import flt

from malta_compliance.vat import books
from malta_compliance.vat.return_form import BASE_ONLY, FINAL, LINES, RESULT, SECTION, SUB, TAX_ONLY, money

INDENT = {SECTION: 0, SUB: 2, FINAL: 0, RESULT: 0}
# Names listed in a note before the rest is counted.
MAX_NAMES = 10
VAT_ACCOUNT_NUMBERS = "1310, 1320, 2210, 2220 and 3230"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	for doctype in ("Sales Invoice", "Purchase Invoice", "GL Entry"):
		frappe.has_permission(doctype, "read", throw=True)
	from_date, to_date = books.period(filters)
	data = books.vat_return(
		filters.company,
		from_date,
		to_date,
		books.cents(filters.adjustment_vat_department),
		books.cents(filters.adjustment_registered_person),
		books.cents(filters.excess_credit_bf),
	)
	return columns(filters), rows(data, filters), "<br>".join(notes(data))


def columns(filters) -> list[dict]:
	result = [
		{"fieldname": "line", "label": _("Line"), "fieldtype": "Data", "width": 560},
		{"fieldname": "box", "label": _("Box"), "fieldtype": "Data", "width": 80},
		{"fieldname": "base", "label": _("Tax Base"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "tax", "label": _("Tax Amount"), "fieldtype": "Currency", "width": 140},
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


def rows(data: books.ReturnData, filters) -> list[dict]:
	"""One row per line of the return; with show_invoices, the invoices of a line follow it. Rows carry the form's
	box numbers of both columns (base_box, tax_box) for scripts reading the report."""
	result = []
	for line in LINES:
		base, tax = data.result.base(line.key), data.result.tax(line.key)
		row = {
			"key": line.key,
			"line": _(line.label),
			"box": line.box,
			"base_box": line.base_box,
			"tax_box": line.tax_box,
			"kind": line.kind,
			"indent": INDENT.get(line.kind, 1),
			"bold": 1 if line.kind in (SECTION, FINAL, RESULT) else 0,
		}
		if line.kind == SECTION:
			row["base"] = row["tax"] = None
		else:
			row["base"] = None if line.columns == TAX_ONLY else flt(base / 100, 2)
			row["tax"] = None if line.columns == BASE_ONLY else flt(tax / 100, 2)
		result.append(row)
		if filters.show_invoices:
			for invoice, entered_base, entered_tax in data.result.entries.get(line.key, []):
				result.append(
					{
						"key": "",
						"line": invoice.party,
						"box": "",
						"kind": "invoice",
						"indent": row["indent"] + 1,
						"bold": 0,
						"posting_date": invoice.posting_date,
						"voucher_type": invoice.doctype,
						"voucher_no": invoice.name,
						"base": flt(entered_base / 100, 2),
						"tax": None if line.columns == BASE_ONLY else flt(entered_tax / 100, 2),
					}
				)
	result[0]["period_label"] = data.label
	return result


def listed(names: list[str]) -> str:
	text = ", ".join(names[:MAX_NAMES])
	if len(names) > MAX_NAMES:
		text += " " + _("and {0} more").format(len(names) - MAX_NAMES)
	return text


def notes(data: books.ReturnData) -> list[str]:
	result = data.result
	lines = [
		_(
			"{0}: submitted Sales and Purchase Invoices of {1} dated {2} to {3}, without opening invoices; {4} "
			"counted, {5} with the category {6}."
		).format(
			data.label,
			data.company,
			frappe.format(data.from_date, {"fieldtype": "Date"}),
			frappe.format(data.to_date, {"fieldtype": "Date"}),
			len(result.counted),
			len(result.outside),
			"VAT No return box",
		)
	]
	if result.unknown:
		lines.append(
			_("Not in the return, without a VAT category of the return: {0}.").format(
				listed([i.name for i in result.unknown])
			)
		)
	if data.drafts:
		lines.append(
			_("Drafts dated in the period, not in the return until submitted: {0}.").format(
				listed(data.drafts)
			)
		)
	booked = _("the invoices as booked give {0}").format(money(result.booked))
	if result.booked != result.tax("26") - result.tax("33"):
		booked += _(", the difference is rounding and goes to Round Off with the settlement entry")
	lines.append(
		_(
			"VAT of purchases (boxes 6, 7, 13 to 15 and 34 to 38) is the rate times the tax base of each line, "
			"unrounded until shown, as in the tax accountant's returns; VAT of sales is the VAT as invoiced. "
			"VAT payable without boxes 40 and 41: {0}, {1}."
		).format(money(result.tax("26") - result.tax("33")), booked)
	)
	lines += result.notes
	if data.ignored_rows:
		lines.append(_("Tax rows not counted as VAT: {0}.").format(listed(data.ignored_rows)))
	if data.differences:
		lines.append(
			_(
				"Ledger check: entries on the VAT accounts {0} not explained by the counted invoices: {1}."
			).format(
				VAT_ACCOUNT_NUMBERS,
				listed([f"{name} ({money(amount)})" for _doctype, name, amount in data.differences]),
			)
		)
	else:
		lines.append(
			_("Ledger check: the VAT accounts {0} moved by the counted invoices only.").format(
				VAT_ACCOUNT_NUMBERS
			)
		)
	lines += settlement_notes(data)
	return lines


def settlement_notes(data: books.ReturnData) -> list[str]:
	if not books.has_settlement_fields():
		return []
	if not data.settlements:
		return [_("Not settled: no settlement entry covers the period.")]
	lines = []
	# VAT payable of the invoices as booked, which a settlement entry clears.
	invoiced = data.result.booked
	for entry in data.settlements:
		state = _("submitted") if entry.docstatus == 1 else _("draft")
		if (entry.from_date, entry.to_date) != (data.from_date, data.to_date):
			lines.append(
				_("The settlement entry {0} ({1}) covers {2} to {3}, which overlaps this period.").format(
					entry.name, state, entry.from_date, entry.to_date
				)
			)
			continue
		lines.append(
			_(
				"Settled by {0} ({1}): VAT payable as filed {2} on {3}; the invoices as booked gave {4} when it was created."
			).format(entry.name, state, money(entry.filed), data.accounts["settlement"], money(entry.cleared))
		)
		if entry.cleared != invoiced:
			lines.append(
				_(
					"The invoices of the period as booked now give {0}: a document of this period was booked, changed or "
					"cancelled after the settlement entry."
				).format(money(invoiced))
			)
	return lines
