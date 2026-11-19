"""Malta VAT setup: the tax categories of vat/categories.py, named after the boxes of the VAT return, per company
the sales and purchase tax templates of a registration under Article 10, and the Journal Entry fields of the VAT
settlement (vat/settlement.py). Article 11 companies charge no VAT and book purchases gross, so they receive no
templates."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from malta_compliance.vat import books
from malta_compliance.vat.categories import ACCOUNTS, BASE, CATEGORIES
from malta_compliance.vat.return_form import LINE

CUSTOM_FIELDS = {
	"Journal Entry": [
		{
			"fieldname": books.FROM_FIELD,
			"label": "VAT Return From",
			"fieldtype": "Date",
			"insert_after": "user_remark",
			"read_only": 1,
			"no_copy": 1,
			"description": "First day of the VAT return period settled by this entry",
		},
		{
			"fieldname": books.TO_FIELD,
			"label": "VAT Return To",
			"fieldtype": "Date",
			"insert_after": books.FROM_FIELD,
			"read_only": 1,
			"no_copy": 1,
			"description": "Last day of the VAT return period settled by this entry",
		},
	]
}


def account(company: str, number: str) -> str:
	name = frappe.db.get_value("Account", {"company": company, "account_number": number, "is_group": 0})
	if not name:
		frappe.throw(f"Account {number} missing in company {company}")
	return name


def ensure_custom_fields() -> None:
	create_custom_fields(CUSTOM_FIELDS, update=True)
	frappe.db.commit()


def after_install() -> None:
	ensure_custom_fields()


def ensure_tax_categories() -> None:
	for title, *_ in CATEGORIES:
		if not frappe.db.exists("Tax Category", title):
			frappe.get_doc({"doctype": "Tax Category", "title": title}).insert(ignore_permissions=True)


def ensure_templates(company: str) -> list[str]:
	"""Creates the missing Article 10 templates of a company; returns the names of the created templates."""
	abbr = frappe.get_cached_value("Company", company, "abbr")
	cost_center = frappe.get_cached_value("Company", company, "cost_center")
	created = []
	for title, direction, _targets, rows in CATEGORIES:
		if not rows:
			continue
		doctype = f"{direction} Taxes and Charges Template"
		if frappe.db.exists(doctype, f"{title} - {abbr}"):
			continue
		taxes = []
		for key, rate, add_deduct in rows:
			row = {
				"charge_type": "On Net Total",
				"account_head": account(company, ACCOUNTS[key]),
				"description": f"VAT {rate}%" + (" reverse charge" if key.endswith("reverse") else ""),
				"rate": rate,
				"cost_center": cost_center,
			}
			if direction == "Purchase":
				row.update({"category": "Total", "add_deduct_tax": add_deduct})
			taxes.append(row)
		doc = frappe.get_doc(
			{"doctype": doctype, "title": title, "company": company, "tax_category": title, "taxes": taxes}
		)
		doc.insert(ignore_permissions=True)
		created.append(doc.name)
	return created


def setup_vat(company: str, vat_article: int) -> list[str]:
	ensure_tax_categories()
	if int(vat_article) == 10:
		return ensure_templates(company)
	return []


def boxes() -> dict[str, dict]:
	"""Boxes of the VAT return per tax category: the boxes of its tax base (net) and of its VAT (tax)."""
	return {
		title: {
			"direction": direction,
			"net": [LINE[line].base_box for line, _sub, _part in targets],
			"tax": [LINE[line].tax_box for line, _sub, part in targets if part != BASE],
		}
		for title, direction, targets, _rows in CATEGORIES
	}
