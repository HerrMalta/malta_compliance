"""Malta VAT setup: the tax categories of vat/categories.py, per company the sales and purchase tax templates of a
registration under Article 10 or the purchase tax templates of a registration under Article 12, the record "Malta
VAT Registration" of a company, and the Journal Entry fields of the VAT settlement (vat/settlement.py). An Article
11 company charges no VAT and books purchases gross, so its own categories have no templates."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from malta_compliance.vat import books, registration
from malta_compliance.vat.categories import (
	ARTICLE_11,
	ARTICLE_12,
	BASE,
	CATEGORIES,
	COST,
	PURCHASE,
	TEMPLATE_ACCOUNTS,
)
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


# Suffix of the description of a template row by its account key.
DESCRIPTION = {
	"input_reverse": " reverse charge",
	"output_reverse": " reverse charge",
	COST: " not deductible",
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
	titles = [title for title, *_ in CATEGORIES] + [c.title for c in (*ARTICLE_11, *ARTICLE_12)]
	for title in titles:
		if not frappe.db.exists("Tax Category", title):
			frappe.get_doc({"doctype": "Tax Category", "title": title}).insert(ignore_permissions=True)


def ensure_template(company: str, title: str, direction: str, rows: tuple) -> str | None:
	"""Creates the template "<title> - <abbreviation>" of a category unless it exists; returns the name of a
	created template."""
	abbr = frappe.get_cached_value("Company", company, "abbr")
	cost_center = frappe.get_cached_value("Company", company, "cost_center")
	doctype = f"{direction} Taxes and Charges Template"
	if frappe.db.exists(doctype, f"{title} - {abbr}"):
		return None
	taxes = []
	for key, rate, add_deduct in rows:
		row = {
			"charge_type": "On Net Total",
			"account_head": account(company, TEMPLATE_ACCOUNTS[key]),
			"description": f"VAT {rate}%" + DESCRIPTION.get(key, ""),
			"rate": rate,
			"cost_center": cost_center,
		}
		if direction == PURCHASE:
			row.update({"category": "Total", "add_deduct_tax": add_deduct})
		taxes.append(row)
	doc = frappe.get_doc(
		{"doctype": doctype, "title": title, "company": company, "tax_category": title, "taxes": taxes}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_templates(company: str) -> list[str]:
	"""Creates the missing Article 10 templates of a company; returns the names of the created templates."""
	created = [
		ensure_template(company, title, direction, rows)
		for title, direction, _targets, rows in CATEGORIES
		if rows
	]
	return [name for name in created if name]


def ensure_article_12_templates(company: str) -> list[str]:
	"""Creates the missing purchase templates of a registration under Article 12; returns the names of the created
	templates."""
	created = [ensure_template(company, c.title, PURCHASE, c.rows) for c in ARTICLE_12]
	return [name for name in created if name]


def ensure_registration(
	company: str,
	vat_article: int,
	number: str | None = None,
	from_date: str | None = None,
	activity: str | None = None,
	article_12_number: str | None = None,
	article_12_from: str | None = None,
) -> bool:
	"""Creates the Malta VAT Registration of a company unless it exists: one registration under the article, and
	one under Article 12 where a number or a first day of it is given. Returns whether a record was created."""
	if frappe.db.exists(registration.DOCTYPE, company):
		return False
	rows = [{"article": f"Article {int(vat_article)}", "registration_number": number, "from_date": from_date}]
	if article_12_number or article_12_from:
		rows.append(
			{
				"article": registration.ARTICLE_12,
				"registration_number": article_12_number,
				"from_date": article_12_from,
			}
		)
	doc = frappe.get_doc({"doctype": registration.DOCTYPE, "company": company, "registrations": rows})
	if activity:
		doc.activity = activity
	doc.insert(ignore_permissions=True)
	return True


def setup_vat(company: str, vat_article: int, article_12: bool = False) -> list[str]:
	"""The tax categories and the templates of the registrations of a company; returns the names of the created
	templates."""
	ensure_tax_categories()
	created = ensure_templates(company) if int(vat_article) == 10 else []
	if article_12:
		created += ensure_article_12_templates(company)
	return created


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
