"""VAT self-charged by a person registered under Article 12 of the Value Added Tax Act: the notices of payment with
their due dates, the payments applied to them and the annual declaration, computed from the purchases with a
category of categories.ARTICLE_12 (rules.py, docs/vat-articles-11-12.md). Imports no Frappe; amounts are cents.
"""

from dataclasses import dataclass
from datetime import date

from malta_compliance.tax.allocation import allocate
from malta_compliance.vat import rules
from malta_compliance.vat.categories import ARTICLE_12_BY_TITLE, GOODS
from malta_compliance.vat.declaration import Document

# Lines of the annual declaration (S.L. 406.09, Seventh Schedule).
EU_SERVICES = "eu_services"
NON_EU_SERVICES = "non_eu_services"
ACQUISITIONS = "acquisitions"
ANNUAL_LINES = (
	(EU_SERVICES, "Services received from the European Union on which VAT is due in Malta"),
	(NON_EU_SERVICES, "Services received from outside the European Union on which VAT is due in Malta"),
	(ACQUISITIONS, "Intra-community acquisitions of goods on which VAT is paid in Malta"),
)


@dataclass(frozen=True)
class Notice:
	"""A purchase in the notice of payment. value: its net total. vat: the VAT self-charged as booked. received:
	the date of the acquisition or of the supply of the service, which is the posting date."""

	document: Document
	kind: str
	eu: bool
	value: int
	vat: int
	invoice_date: date
	received: date
	due: date

	@property
	def line(self) -> str:
		"""Line of the annual declaration."""
		if self.kind == GOODS:
			return ACQUISITIONS
		return EU_SERVICES if self.eu else NON_EU_SERVICES


@dataclass(frozen=True)
class Settled:
	"""A notice with the payments applied to it: the amount paid, the date of the last payment and the open rest."""

	notice: Notice
	paid: int
	paid_on: date | None
	open: int


def payment_day(on: date, months: int) -> date:
	"""The payment day of the month `months` months after the month of a date."""
	index = on.year * 12 + on.month - 1 + months
	return date(index // 12, index % 12 + 1, rules.PAYMENT_DAY)


def goods_due(acquired: date, invoiced: date) -> date:
	"""Due date of the VAT on an intra-community acquisition: the 15th day of the month after the month in which
	the tax becomes chargeable (art. 21(2)). It becomes chargeable on the date of the invoice or, where earlier,
	on the 15th day of the month after the acquisition (Fourth Schedule, item 6)."""
	return payment_day(min(invoiced, payment_day(acquired, 1)), 1)


def services_due(received: date, invoiced: date) -> date:
	"""Due date of the VAT on a service whose VAT the customer pays: the 15th day of the second month after the
	month of the invoice or, where earlier, of the supply (art. 21(3))."""
	return payment_day(min(invoiced, received), 2)


def notice(document: Document) -> Notice:
	"""The notice entry of a purchase with a category of Article 12. Raises rules.NotCovered for a purchase dated
	before its kind required a registration under Article 12."""
	category = ARTICLE_12_BY_TITLE[document.category]
	received = document.posting_date
	invoiced = document.invoice_date or received
	start = (
		rules.ARTICLE_12_GOODS_FROM if category.kind == GOODS else rules.ARTICLE_12_SERVICES_RECEIVED_FROM
	)
	if received < start:
		raise rules.NotCovered(
			f"{document.name}: {category.kind.lower()} dated {received.isoformat()}, before Article 12 covered "
			f"them ({start.isoformat()})"
		)
	due = goods_due(received, invoiced) if category.kind == GOODS else services_due(received, invoiced)
	return Notice(document, category.kind, category.eu, document.net, document.vat, invoiced, received, due)


def notices(documents: list[Document]) -> list[Notice]:
	"""The notice entries of the purchases with a category of Article 12, by due date."""
	found = [notice(d) for d in documents if d.category in ARTICLE_12_BY_TITLE]
	return sorted(found, key=lambda n: (n.due, n.received, n.document.name))


def settle(entries: list[Notice], payments: list[tuple[date, int]]) -> tuple[list[Settled], int]:
	"""Applies the payments in date order to the notices in the order of their due dates. A notice with negative
	VAT, such as a supplier's credit note, counts as a payment on its date. Returns the notices in the given order
	and the excess of the payments over the VAT due."""
	due = [n for n in entries if n.vat > 0]
	credits = [(n.received, -n.vat) for n in entries if n.vat < 0]
	parts, excess = allocate([n.vat for n in due], [*payments, *credits])
	applied = {n.document.name: p for n, p in zip(due, parts, strict=True)}
	result = []
	for entry in entries:
		paid_parts = applied.get(entry.document.name, []) if entry.vat > 0 else []
		paid = int(sum(amount for _paid_on, amount in paid_parts))
		result.append(
			Settled(
				entry,
				paid,
				max((paid_on for paid_on, _amount in paid_parts), default=None),
				max(entry.vat, 0) - paid,
			)
		)
	return result, int(excess)


def annual(entries: list[Notice], year: int) -> dict[str, list[int]]:
	"""Value and VAT per line of the annual declaration: the acquisitions and services received in the year."""
	lines = {key: [0, 0] for key, _label in ANNUAL_LINES}
	for entry in entries:
		if entry.received.year == year:
			lines[entry.line][0] += entry.value
			lines[entry.line][1] += entry.vat
	return lines

