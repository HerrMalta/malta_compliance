"""Declaration of a registration under Article 11 of the Value Added Tax Act for a calendar year, computed from the
invoices by their tax categories (categories.ARTICLE_11, ARTICLE_12), with the tests of the turnover limit of a
small enterprise and of the acquisitions threshold (rules.py, docs/vat-articles-11-12.md). Imports no Frappe;
amounts are cents of the company currency, which is the euro.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from malta_compliance.vat import rules
from malta_compliance.vat.categories import (
	ARTICLE_11_BOXES,
	ARTICLE_11_BY_TITLE,
	ARTICLE_12_BY_TITLE,
	GOODS,
	NO_RETURN_BOX,
	PURCHASE,
	SALES,
	TURNOVER_MALTA,
)

DIRECTION_OF = {"Sales Invoice": SALES, "Purchase Invoice": PURCHASE}


@dataclass(frozen=True)
class Document:
	"""A submitted invoice. amount: the total as invoiced of a sale; of a purchase the total payable to the supplier
	plus the VAT self-charged under Article 12, which is its cost. net: the net total. vat: the VAT self-charged.
	invoice_date: the date of the supplier's invoice, where it differs from the posting date."""

	doctype: str
	name: str
	posting_date: date
	party: str
	category: str
	amount: int
	net: int = 0
	vat: int = 0
	invoice_date: date | None = None


@dataclass
class Declaration:
	"""boxes: amount per box of the declaration. entries: the invoices of each box. outside: invoices of a category
	without a box. unknown: invoices without a category of an Article 11 company, or with a category of the other
	direction."""

	boxes: dict[str, int]
	entries: dict[str, list[Document]] = field(default_factory=dict)
	outside: list[Document] = field(default_factory=list)
	unknown: list[Document] = field(default_factory=list)


@dataclass(frozen=True)
class LimitTest:
	"""A value from first to last against a limit, both in cents. limit None: no limit applies to the period.
	exceeded_on: the posting date of the invoice with which a value counted over a calendar year exceeds the
	limit. preceding: the test of the preceding calendar year, the condition of an application."""

	label: str
	first: date
	last: date
	value: int
	limit: int | None
	exceeded: bool
	source: str
	exceeded_on: date | None = None
	preceding: bool = False


def box_of(document: Document) -> tuple[bool, str | None]:
	"""Whether the invoice carries a category of an Article 11 company in its direction, and its box."""
	direction = DIRECTION_OF.get(document.doctype)
	category = ARTICLE_11_BY_TITLE.get(document.category)
	if category:
		return category.direction == direction, category.box
	if direction == PURCHASE:
		if document.category in ARTICLE_12_BY_TITLE:
			return True, ARTICLE_12_BY_TITLE[document.category].box
		if document.category == NO_RETURN_BOX:
			return True, None
	return False, None


def declaration(documents: list[Document]) -> Declaration:
	"""The boxes of the declaration from the invoices of its period."""
	result = Declaration(boxes={box: 0 for box, _label in ARTICLE_11_BOXES})
	for document in documents:
		known, box = box_of(document)
		if not known:
			result.unknown.append(document)
		elif box is None:
			result.outside.append(document)
		else:
			result.boxes[box] += document.amount
			result.entries.setdefault(box, []).append(document)
	return result


def is_turnover(document: Document, version: rules.SmallEnterprise) -> bool:
	"""Whether a sale counts towards the turnover measured against the limits of the version."""
	category = ARTICLE_11_BY_TITLE.get(document.category)
	if not category or not category.turnover or DIRECTION_OF.get(document.doctype) != SALES:
		return False
	return category.turnover == TURNOVER_MALTA or not version.domestic


def turnover(documents: list[Document], first: date, last: date, version: rules.SmallEnterprise) -> int:
	"""Turnover of the invoices posted from first to last."""
	return sum(d.amount for d in documents if first <= d.posting_date <= last and is_turnover(d, version))


def quarter_start(on: date) -> date:
	"""First day of the calendar quarter of a date."""
	return date(on.year, 3 * ((on.month - 1) // 3) + 1, 1)


def next_quarter(start: date) -> date:
	"""First day of the calendar quarter after the one starting on `start`."""
	return date(start.year + 1, 1, 1) if start.month == 10 else date(start.year, start.month + 3, 1)


def relevant_period(on: date, started: date | None = None) -> tuple[date, date, int] | None:
	"""First day, last day and number of calendar quarters of the relevant period on a date: the twelve months
	ending on the last day of the calendar quarter before the quarter of the date. For an activity started within
	these months the period begins with the quarter after the quarter of the start; None while it holds no quarter
	(Sixth Schedule as in force until 2024, Part One item 5)."""
	end = quarter_start(on)
	first = date(end.year - 1, end.month, 1)
	quarters = 4
	if started and started > first:
		first = next_quarter(quarter_start(started))
		quarters = ((end.year - first.year) * 12 + end.month - first.month) // 3
		if quarters < 1:
			return None
	return first, end - timedelta(days=1), quarters


def exceeded_on(documents: list[Document], limit: int, below: bool) -> date | None:
	"""Posting date of the invoice with which the running total of the invoices, in date order, leaves the limit."""
	total = 0
	for document in sorted(documents, key=lambda d: (d.posting_date, d.name)):
		total += document.amount
		if rules.exceeds(total, limit, below):
			return document.posting_date
	return None


def limit_tests(
	documents: list[Document], year: int, activity: str, started: date | None = None
) -> list[LimitTest]:
	"""Tests of the turnover limit of a registered person in a calendar year. Until 2024: on the first day of each
	calendar quarter, the turnover of the relevant period against the limit of that day, reduced in proportion for
	a period of fewer than four quarters. From 2025: the turnover of the calendar year, and that of the preceding
	calendar year, which is the condition of an application. Raises rules.NotCovered."""
	tests = []
	for month in (1, 4, 7, 10):
		on = date(year, month, 1)
		version = rules.small_enterprise(on)
		if version.period == rules.CALENDAR_YEAR:
			return [*calendar_year_tests(documents, year, activity, version), *tests]
		period = relevant_period(on, started)
		if period is None:
			continue
		first, last, quarters = period
		value = turnover(documents, first, last, version)
		limit = version.stay_limit(activity) * quarters // 4
		tests.append(
			LimitTest(
				f"{'12 months' if quarters == 4 else f'{quarters * 3} months'} to {last.day} {last:%b %Y}",
				first,
				last,
				value,
				limit,
				rules.exceeds(value, limit, version.stay_below),
				version.source,
			)
		)
	return tests


def calendar_year_tests(
	documents: list[Document], year: int, activity: str, version: rules.SmallEnterprise
) -> list[LimitTest]:
	counted = [d for d in documents if is_turnover(d, version)]
	tests = []
	for tested, limit, below in (
		(year, version.stay_limit(activity), version.stay_below),
		(year - 1, version.entry_limit(activity), version.entry_below),
	):
		of_year = [d for d in counted if d.posting_date.year == tested]
		crossed = exceeded_on(of_year, limit, below)
		value = sum(d.amount for d in of_year)
		tests.append(
			LimitTest(
				f"Calendar year {tested}",
				date(tested, 1, 1),
				date(tested, 12, 31),
				value,
				limit,
				crossed is not None,
				version.source,
				crossed,
				preceding=tested != year,
			)
		)
	return tests


def is_acquisition(document: Document) -> bool:
	"""Whether a purchase is an acquisition of goods from another Member State."""
	if DIRECTION_OF.get(document.doctype) != PURCHASE:
		return False
	small = ARTICLE_11_BY_TITLE.get(document.category)
	charged = ARTICLE_12_BY_TITLE.get(document.category)
	return bool((small and small.eu_goods) or (charged and charged.kind == GOODS and charged.eu))


def acquisitions(documents: list[Document], year: int) -> LimitTest | None:
	"""The acquisitions of goods from other Member States of a calendar year against the acquisitions threshold;
	None before the accession. A purchase under Article 12 counts with its net total, any other with its amount
	as booked, which holds the VAT of the other Member State."""
	if year < rules.ARTICLE_12_GOODS_FROM.year:
		return None
	first = max(date(year, 1, 1), rules.ARTICLE_12_GOODS_FROM)
	last = date(year, 12, 31)
	valued = [
		Document(d.doctype, d.name, d.posting_date, d.party, d.category, acquisition_value(d))
		for d in documents
		if first <= d.posting_date <= last and is_acquisition(d)
	]
	limit = rules.ACQUISITIONS_THRESHOLD * 100
	crossed = exceeded_on(valued, limit, False)
	return LimitTest(
		f"Calendar year {year}",
		first,
		last,
		sum(d.amount for d in valued),
		limit,
		crossed is not None,
		rules.ACQUISITIONS_SOURCE,
		crossed,
	)


def acquisition_value(document: Document) -> int:
	return document.net if document.category in ARTICLE_12_BY_TITLE else document.amount


def eu_customer_services(documents: list[Document], year: int) -> list[Document]:
	"""Services of the year supplied to customers in other Member States who pay the VAT, dated from the day such
	a supply requires a registration under Article 12."""
	return [
		d
		for d in documents
		if d.posting_date.year == year
		and d.posting_date >= rules.ARTICLE_12_SERVICES_SUPPLIED_FROM
		and DIRECTION_OF.get(d.doctype) == SALES
		and getattr(ARTICLE_11_BY_TITLE.get(d.category), "eu_customer", False)
	]
