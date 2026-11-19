"""Tax categories of the Maltese VAT return, named after its boxes: per category the direction, the lines of the
return it enters (return_form.LINES) and the rows of its Article 10 tax template. An invoice carries one category.
Imports no Frappe.
"""

# Account numbers in setup/chart_self_employed.json.
ACCOUNTS = {
	"input": "1310",
	"input_reverse": "1320",
	"output": "2210",
	"output_reverse": "2220",
	"private_vat": "3230",
}
INPUT_ACCOUNTS = ("input", "input_reverse")
OUTPUT_ACCOUNTS = ("output", "output_reverse")

# VAT of an invoice entering a line: none (tax base only), the output VAT charged or self-charged, or the input VAT
# deducted.
BASE = "base"
OUTPUT = "output"
INPUT = "input"

# Sub-line selector: the sub-line of the line whose rate equals the rate of the invoice's VAT rows.
RATE = "rate"

NO_RETURN_BOX = "VAT No return box"
SALES = "Sales"
PURCHASE = "Purchase"

REVERSE_CHARGE_18 = (("input_reverse", 18, "Add"), ("output_reverse", 18, "Deduct"))

# (tax category, direction, targets as (line key, sub-line key or RATE or None, VAT part), template rows as
# (account key, rate in percent, Add or Deduct)). A category without rows has no template; its invoices carry no
# taxes.
CATEGORIES = (
	("VAT Box 1 EU business customer liable", SALES, (("1", None, BASE),), (("output", 0, "Add"),)),
	("VAT Box 2 Supply outside Malta", SALES, (("2", None, BASE),), (("output", 0, "Add"),)),
	("VAT Box 18/23 Malta 18%", SALES, (("18", "18_taxable", OUTPUT),), (("output", 18, "Add"),)),
	("VAT Box 18a/23a Malta 7%", SALES, (("18a", None, OUTPUT),), (("output", 7, "Add"),)),
	("VAT Box 18b/23b Malta 12%", SALES, (("18b", None, OUTPUT),), (("output", 12, "Add"),)),
	("VAT Box 19/24 Malta 5%", SALES, (("19", None, OUTPUT),), (("output", 5, "Add"),)),
	("VAT Box 20 Exempt with credit or export", SALES, (("20", None, BASE),), (("output", 0, "Add"),)),
	("VAT Box 21 Exempt without credit", SALES, (("21", None, BASE),), (("output", 0, "Add"),)),
	(
		"VAT Box 3/6 9/13 EU goods for resale reverse charge",
		PURCHASE,
		(("3", "3_ic", OUTPUT), ("9", RATE, INPUT)),
		REVERSE_CHARGE_18,
	),
	(
		"VAT Box 3/6 9a/13a EU services reverse charge",
		PURCHASE,
		(("3", "3_ic", OUTPUT), ("9a", None, INPUT)),
		REVERSE_CHARGE_18,
	),
	(
		"VAT Box 3/6 10/14 EU capital goods reverse charge",
		PURCHASE,
		(("3", "3_ic", OUTPUT), ("10", RATE, INPUT)),
		REVERSE_CHARGE_18,
	),
	(
		"VAT Box 4/7 11/15 Non-EU services reverse charge",
		PURCHASE,
		(("4", "4_malta", OUTPUT), ("11", None, INPUT)),
		REVERSE_CHARGE_18,
	),
	# Goods for private use bought from another EU state under the VAT number: VAT payable, no deduction (box 17).
	(
		"VAT Box 3/6 EU goods for private use not deductible",
		PURCHASE,
		(("3", RATE, OUTPUT),),
		(("private_vat", 18, "Add"), ("output_reverse", 18, "Deduct")),
	),
	("VAT Box 27/34 Malta goods for resale 18%", PURCHASE, (("27", None, INPUT),), (("input", 18, "Add"),)),
	("VAT Box 28/35 Malta goods for resale 5%", PURCHASE, (("28", None, INPUT),), (("input", 5, "Add"),)),
	("VAT Box 29 Malta exempt purchases for resale", PURCHASE, (("29", None, BASE),), ()),
	("VAT Box 30/36 Malta capital goods 18%", PURCHASE, (("30", RATE, INPUT),), (("input", 18, "Add"),)),
	(
		"VAT Box 31/37 Malta services and overheads 18%",
		PURCHASE,
		(("31", None, INPUT),),
		(("input", 18, "Add"),),
	),
	(
		"VAT Box 31a/37a Malta services and overheads 7%",
		PURCHASE,
		(("31a", None, INPUT),),
		(("input", 7, "Add"),),
	),
	(
		"VAT Box 31b/37b Malta services and overheads 12%",
		PURCHASE,
		(("31b", None, INPUT),),
		(("input", 12, "Add"),),
	),
	(
		"VAT Box 32/38 Malta services and overheads 5%",
		PURCHASE,
		(("32", None, INPUT),),
		(("input", 5, "Add"),),
	),
	(NO_RETURN_BOX, PURCHASE, (), ()),
)

# Former names of categories, renamed by the patch of the version given.
RENAMED = {"VAT Box 18/24 Malta 5%": ("VAT Box 19/24 Malta 5%", "0.5.0")}

TARGETS = {title: targets for title, _direction, targets, _rows in CATEGORIES}
DIRECTION = {title: direction for title, direction, _targets, _rows in CATEGORIES}
# Rate of the category's tax template, for invoices whose VAT rows carry an amount without a rate.
TEMPLATE_RATE = {title: rows[0][1] for title, _direction, _targets, rows in CATEGORIES if rows}
