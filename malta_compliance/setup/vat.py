"""Malta VAT setup: tax categories named after the boxes of the VAT return (box numbers as in the tax accountant's
return form), and per company the sales and purchase tax templates of a registration under Article 10. An invoice
carries one tax category; the quarterly return sums net and tax amounts per category into the listed boxes.
Article 11 companies charge no VAT and book purchases gross, so they receive no templates."""

import frappe

# Account numbers in chart_self_employed.json.
ACCOUNTS = {
	"input": "1310",
	"input_reverse": "1320",
	"output": "2210",
	"output_reverse": "2220",
	"private_vat": "3230",
}

REVERSE_CHARGE_18 = (("input_reverse", 18, "Add"), ("output_reverse", 18, "Deduct"))

# (tax category, direction, boxes for the net amount, boxes for the tax amount, template rows as (account key,
# rate in percent, Add or Deduct)). A category without rows has no template; its invoices carry no taxes.
CATEGORIES = (
	("VAT Box 1 EU business customer liable", "Sales", ("1",), (), (("output", 0, "Add"),)),
	("VAT Box 2 Supply outside Malta", "Sales", ("2",), (), (("output", 0, "Add"),)),
	("VAT Box 18/23 Malta 18%", "Sales", ("18",), ("23",), (("output", 18, "Add"),)),
	("VAT Box 18a/23a Malta 7%", "Sales", ("18a",), ("23a",), (("output", 7, "Add"),)),
	("VAT Box 18b/23b Malta 12%", "Sales", ("18b",), ("23b",), (("output", 12, "Add"),)),
	("VAT Box 18/24 Malta 5%", "Sales", ("18 (5%)",), ("24",), (("output", 5, "Add"),)),
	("VAT Box 20 Exempt with credit or export", "Sales", ("20",), (), (("output", 0, "Add"),)),
	("VAT Box 21 Exempt without credit", "Sales", ("21",), (), (("output", 0, "Add"),)),
	("VAT Box 3/6 9/13 EU goods for resale reverse charge", "Purchase", ("3", "9"), ("6", "13"), REVERSE_CHARGE_18),
	("VAT Box 3/6 9a/13a EU services reverse charge", "Purchase", ("3", "9a"), ("6", "13a"), REVERSE_CHARGE_18),
	("VAT Box 3/6 10/14 EU capital goods reverse charge", "Purchase", ("3", "10"), ("6", "14"), REVERSE_CHARGE_18),
	("VAT Box 4/7 11/15 Non-EU services reverse charge", "Purchase", ("4", "11"), ("7", "15"), REVERSE_CHARGE_18),
	# Goods for private use bought from another EU state under the VAT number: VAT payable, no deduction (box 17).
	("VAT Box 3/6 EU goods for private use not deductible", "Purchase", ("3",), ("6",), (("private_vat", 18, "Add"), ("output_reverse", 18, "Deduct"))),
	("VAT Box 27/34 Malta goods for resale 18%", "Purchase", ("27",), ("34",), (("input", 18, "Add"),)),
	("VAT Box 28/35 Malta goods for resale 5%", "Purchase", ("28",), ("35",), (("input", 5, "Add"),)),
	("VAT Box 29 Malta exempt purchases for resale", "Purchase", ("29",), (), ()),
	("VAT Box 30/36 Malta capital goods 18%", "Purchase", ("30",), ("36",), (("input", 18, "Add"),)),
	("VAT Box 31/37 Malta services and overheads 18%", "Purchase", ("31",), ("37",), (("input", 18, "Add"),)),
	("VAT Box 31a/37a Malta services and overheads 7%", "Purchase", ("31a",), ("37a",), (("input", 7, "Add"),)),
	("VAT Box 31b/37b Malta services and overheads 12%", "Purchase", ("31b",), ("37b",), (("input", 12, "Add"),)),
	("VAT Box 32/38 Malta services and overheads 5%", "Purchase", ("32",), ("38",), (("input", 5, "Add"),)),
	("VAT No return box", "Purchase", (), (), ()),
)


def account(company: str, number: str) -> str:
	name = frappe.db.get_value("Account", {"company": company, "account_number": number, "is_group": 0})
	if not name:
		frappe.throw(f"Account {number} missing in company {company}")
	return name


def ensure_tax_categories() -> None:
	for title, *_ in CATEGORIES:
		if not frappe.db.exists("Tax Category", title):
			frappe.get_doc({"doctype": "Tax Category", "title": title}).insert(ignore_permissions=True)


def ensure_templates(company: str) -> list[str]:
	"""Creates the missing Article 10 templates of a company; returns the names of the created templates."""
	abbr = frappe.get_cached_value("Company", company, "abbr")
	cost_center = frappe.get_cached_value("Company", company, "cost_center")
	created = []
	for title, direction, _net_boxes, _tax_boxes, rows in CATEGORIES:
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
		doc = frappe.get_doc({"doctype": doctype, "title": title, "company": company, "tax_category": title, "taxes": taxes})
		doc.insert(ignore_permissions=True)
		created.append(doc.name)
	return created


def setup_vat(company: str, vat_article: int) -> list[str]:
	ensure_tax_categories()
	if int(vat_article) == 10:
		return ensure_templates(company)
	return []


def boxes() -> dict[str, dict]:
	"""Box assignment per tax category, for the VAT return report."""
	return {
		title: {"direction": direction, "net": list(net), "tax": list(tax)}
		for title, direction, net, tax, _rows in CATEGORIES
	}
