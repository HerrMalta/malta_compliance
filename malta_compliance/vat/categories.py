"""Tax categories of the Maltese VAT return, named after its boxes: per category the direction, the lines of the
return it enters (return_form.LINES) and the rows of its Article 10 tax template; and the tax categories of the
registrations under Articles 11 and 12 (ARTICLE_11, ARTICLE_12). An invoice carries one category. Imports no Frappe.
"""

from dataclasses import dataclass

# VAT accounts, by their numbers in setup/chart_self_employed.json.
ACCOUNTS = {
	"input": "1310",
	"input_reverse": "1320",
	"output": "2210",
	"output_reverse": "2220",
	"private_vat": "3230",
}
INPUT_ACCOUNTS = ("input", "input_reverse")
OUTPUT_ACCOUNTS = ("output", "output_reverse")
# Account of self-charged VAT that is not deductible on a business purchase (VAT Act, Tenth Schedule, items 3 and
# 5(2)): an expense. For a fixed asset the row is booked on the asset's fixed asset account instead, as part of the
# asset's cost.
COST = "non_recoverable"
TEMPLATE_ACCOUNTS = {**ACCOUNTS, COST: "5960"}

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


def reverse_charge(rate: int) -> tuple:
	"""Template rows of a reverse charge at a Maltese rate: input and output VAT, net zero."""
	return (("input_reverse", rate, "Add"), ("output_reverse", rate, "Deduct"))


def not_deductible(rate: int, cost: str = COST) -> tuple:
	"""Template rows of self-charged VAT without deduction: its cost, and the VAT payable."""
	return ((cost, rate, "Add"), ("output_reverse", rate, "Deduct"))


# Targets of the reverse charges and of self-charged VAT without deduction.
EU_RESALE = (("3", "3_ic", OUTPUT), ("9", RATE, INPUT))
EU_SERVICES = (("3", "3_ic", OUTPUT), ("9a", None, INPUT))
EU_CAPITAL = (("3", "3_ic", OUTPUT), ("10", RATE, INPUT))
NON_EU_SERVICES = (("4", "4_malta", OUTPUT), ("11", None, INPUT))
EU_NOT_DEDUCTIBLE = (("3", RATE, OUTPUT),)
NON_EU_NOT_DEDUCTIBLE = (("4", "4_nr", OUTPUT),)

# (tax category, direction, targets as (line key, sub-line key or RATE or None, VAT part), template rows as
# (account key of TEMPLATE_ACCOUNTS, rate in percent, Add or Deduct)). A RATE target enters the sub-line of the
# rate of the invoice's VAT rows. A category without rows has no template; its invoices carry no taxes. A reverse
# charge is at the Maltese rate of the goods or services (VAT Act art. 19, Eighth Schedule); a reverse-charge
# category without a rate in its name is at 18%.
CATEGORIES = (
	("VAT Box 1 EU business customer liable", SALES, (("1", None, BASE),), (("output", 0, "Add"),)),
	("VAT Box 2 Supply outside Malta", SALES, (("2", None, BASE),), (("output", 0, "Add"),)),
	("VAT Box 18/23 Malta 18%", SALES, (("18", "18_taxable", OUTPUT),), (("output", 18, "Add"),)),
	# A supply under the Commissioner's direction that the customer pays its VAT (VAT Act, Fourteenth Schedule,
	# Part Five): taxable at 18%, invoiced without VAT; box 18 holds its value, box 23 no tax.
	(
		"VAT Box 18 Malta tax in danger customer liable",
		SALES,
		(("18", "18_danger", BASE),),
		(("output", 0, "Add"),),
	),
	("VAT Box 18a/23a Malta 7%", SALES, (("18a", None, OUTPUT),), (("output", 7, "Add"),)),
	("VAT Box 18b/23b Malta 12%", SALES, (("18b", None, OUTPUT),), (("output", 12, "Add"),)),
	("VAT Box 19/24 Malta 5%", SALES, (("19", None, OUTPUT),), (("output", 5, "Add"),)),
	("VAT Box 20 Exempt with credit or export", SALES, (("20", None, BASE),), (("output", 0, "Add"),)),
	("VAT Box 21 Exempt without credit", SALES, (("21", None, BASE),), (("output", 0, "Add"),)),
	("VAT Box 3/6 9/13 EU goods for resale reverse charge", PURCHASE, EU_RESALE, reverse_charge(18)),
	("VAT Box 3/6 9/13 EU goods for resale reverse charge 5%", PURCHASE, EU_RESALE, reverse_charge(5)),
	# Acquisitions of goods whose supply in Malta is always exempt, such as food and pharmaceuticals (VAT Act art.
	# 9(1)(b), Fifth Schedule, Part Three, items 2 and 5): value in boxes 3 and 9, no VAT.
	(
		"VAT Box 3/6 9/13 EU goods for resale exempt 0%",
		PURCHASE,
		(("3", "3_ic", BASE), ("9", "9_rc0", BASE)),
		(),
	),
	("VAT Box 3/6 9a/13a EU services reverse charge", PURCHASE, EU_SERVICES, reverse_charge(18)),
	("VAT Box 3/6 9a/13a EU services reverse charge 5%", PURCHASE, EU_SERVICES, reverse_charge(5)),
	("VAT Box 3/6 9a/13a EU services reverse charge 12%", PURCHASE, EU_SERVICES, reverse_charge(12)),
	("VAT Box 3/6 10/14 EU capital goods reverse charge", PURCHASE, EU_CAPITAL, reverse_charge(18)),
	("VAT Box 3/6 10/14 EU capital goods reverse charge 5%", PURCHASE, EU_CAPITAL, reverse_charge(5)),
	("VAT Box 4/7 11/15 Non-EU services reverse charge", PURCHASE, NON_EU_SERVICES, reverse_charge(18)),
	("VAT Box 4/7 11/15 Non-EU services reverse charge 5%", PURCHASE, NON_EU_SERVICES, reverse_charge(5)),
	("VAT Box 4/7 11/15 Non-EU services reverse charge 12%", PURCHASE, NON_EU_SERVICES, reverse_charge(12)),
	# Self-charged VAT without deduction, in boxes 3/6 or 4/7 only and payable through box 17: purchases whose VAT
	# is not input tax (VAT Act, Tenth Schedule, item 3: tobacco, alcohol, works of art, motor vehicles, vessels and
	# aircraft with their upkeep, entertainment and hospitality; item 5(2): use for exempt supplies without credit),
	# and goods or services acquired under the VAT number for private use, whose VAT is held on 3230.
	("VAT Box 3/6 EU purchases not deductible 18%", PURCHASE, EU_NOT_DEDUCTIBLE, not_deductible(18)),
	("VAT Box 3/6 EU purchases not deductible 5%", PURCHASE, EU_NOT_DEDUCTIBLE, not_deductible(5)),
	(
		"VAT Box 3/6 EU goods for private use not deductible",
		PURCHASE,
		EU_NOT_DEDUCTIBLE,
		not_deductible(18, "private_vat"),
	),
	(
		"VAT Box 3/6 EU goods for private use not deductible 5%",
		PURCHASE,
		EU_NOT_DEDUCTIBLE,
		not_deductible(5, "private_vat"),
	),
	("VAT Box 4/7 Non-EU services not deductible", PURCHASE, NON_EU_NOT_DEDUCTIBLE, not_deductible(18)),
	(
		"VAT Box 4/7 Non-EU services for private use not deductible",
		PURCHASE,
		NON_EU_NOT_DEDUCTIBLE,
		not_deductible(18, "private_vat"),
	),
	("VAT Box 27/34 Malta goods for resale 18%", PURCHASE, (("27", None, INPUT),), (("input", 18, "Add"),)),
	("VAT Box 28/35 Malta goods for resale 5%", PURCHASE, (("28", None, INPUT),), (("input", 5, "Add"),)),
	("VAT Box 29 Malta exempt purchases for resale", PURCHASE, (("29", None, BASE),), ()),
	("VAT Box 30/36 Malta capital goods 18%", PURCHASE, (("30", RATE, INPUT),), (("input", 18, "Add"),)),
	("VAT Box 30/36 Malta capital goods 5%", PURCHASE, (("30", RATE, INPUT),), (("input", 5, "Add"),)),
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

# Former names of categories and the version whose patch renames them.
RENAMED = {"VAT Box 18/24 Malta 5%": ("VAT Box 19/24 Malta 5%", "0.5.0")}

TARGETS = {title: targets for title, _direction, targets, _rows in CATEGORIES}
DIRECTION = {title: direction for title, direction, _targets, _rows in CATEGORIES}
# Rate of the category's tax template, for invoices whose VAT rows carry an amount without a rate.
TEMPLATE_RATE = {title: rows[0][1] for title, _direction, _targets, rows in CATEGORIES if rows}
# Categories whose self-charged VAT is a cost of the purchase: their Add row is booked on an expense or fixed asset
# account, which is not a VAT account.
NOT_DEDUCTIBLE = frozenset(
	title for title, _direction, _targets, rows in CATEGORIES if any(key == COST for key, *_ in rows)
)


# Registrations under Articles 11 and 12 (docs/vat-articles-11-12.md). An Article 11 company charges no VAT and
# deducts none: its invoices carry a category of ARTICLE_11, or NO_RETURN_BOX for a purchase outside the
# declaration, and no VAT rows. A purchase whose VAT the company self-charges carries a category of ARTICLE_12.

# How a sale counts towards the turnover of the small-enterprise limit (rules.SmallEnterprise.domestic).
TURNOVER_MALTA = "malta"  # place of supply in Malta: counted in every period
TURNOVER_OUTSIDE = "outside"  # place of supply outside Malta: counted until 2024

# Kinds of a purchase under Article 12, as in the notice of payment.
SERVICES = "Services"
GOODS = "Goods"

# Boxes of the declaration of an Article 11 registration (S.L. 406.09, Fifth Schedule).
ARTICLE_11_BOXES = (
	("1", "Sale of Goods"),
	("2", "Provision of Services"),
	("3", "Purchases of stock for re-sale"),
	("4", "Purchases of capital assets during the year"),
)


@dataclass(frozen=True)
class Article11Category:
	"""Tax category of an Article 11 company. box: box of the declaration, None for none. turnover: TURNOVER_MALTA
	or TURNOVER_OUTSIDE for a sale counted towards the small-enterprise limit, None otherwise. eu_customer: a
	service whose VAT the customer in another Member State pays. eu_goods: goods acquired from another Member
	State with the VAT of that State, counted towards the acquisitions threshold."""

	title: str
	direction: str
	box: str | None
	turnover: str | None = None
	eu_customer: bool = False
	eu_goods: bool = False


@dataclass(frozen=True)
class Article12Category:
	"""Tax category of a purchase whose VAT is self-charged under Article 12 at `rate` percent, without deduction.
	kind: SERVICES or GOODS. eu: supplier in another Member State. box: box of the Article 11 declaration."""

	title: str
	kind: str
	eu: bool
	rate: int
	box: str | None = None

	@property
	def rows(self) -> tuple:
		"""Rows of the tax template: the VAT as a cost of the purchase, and the VAT payable."""
		return not_deductible(self.rate)


ARTICLE_11 = (
	Article11Category("VAT Art 11 Box 1 Sale of goods", SALES, "1", TURNOVER_MALTA),
	# A disposal of a capital asset is outside the turnover (Sixth Schedule, definition 3(2)).
	Article11Category("VAT Art 11 Box 1 Sale of capital asset", SALES, "1"),
	Article11Category("VAT Art 11 Box 2 Services in Malta", SALES, "2", TURNOVER_MALTA),
	Article11Category(
		"VAT Art 11 Box 2 Services EU business customer liable", SALES, "2", TURNOVER_OUTSIDE, eu_customer=True
	),
	Article11Category("VAT Art 11 Box 2 Services outside Malta", SALES, "2", TURNOVER_OUTSIDE),
	Article11Category("VAT Art 11 Box 3 Stock for re-sale", PURCHASE, "3"),
	Article11Category("VAT Art 11 Box 3 Stock for re-sale from EU", PURCHASE, "3", eu_goods=True),
	Article11Category("VAT Art 11 Box 4 Capital assets", PURCHASE, "4"),
	Article11Category("VAT Art 11 Box 4 Capital assets from EU", PURCHASE, "4", eu_goods=True),
	Article11Category("VAT Art 11 EU goods", PURCHASE, None, eu_goods=True),
)

ARTICLE_12 = (
	Article12Category("VAT Art 12 EU services 18%", SERVICES, True, 18),
	Article12Category("VAT Art 12 EU services 5%", SERVICES, True, 5),
	Article12Category("VAT Art 12 EU services 12%", SERVICES, True, 12),
	Article12Category("VAT Art 12 Non-EU services 18%", SERVICES, False, 18),
	Article12Category("VAT Art 12 Non-EU services 5%", SERVICES, False, 5),
	Article12Category("VAT Art 12 Non-EU services 12%", SERVICES, False, 12),
	Article12Category("VAT Art 12 EU goods 18%", GOODS, True, 18),
	Article12Category("VAT Art 12 EU goods 5%", GOODS, True, 5),
	Article12Category("VAT Art 12 EU goods for re-sale 18%", GOODS, True, 18, "3"),
	Article12Category("VAT Art 12 EU goods for re-sale 5%", GOODS, True, 5, "3"),
	Article12Category("VAT Art 12 EU capital goods 18%", GOODS, True, 18, "4"),
)

ARTICLE_11_BY_TITLE = {category.title: category for category in ARTICLE_11}
ARTICLE_12_BY_TITLE = {category.title: category for category in ARTICLE_12}
