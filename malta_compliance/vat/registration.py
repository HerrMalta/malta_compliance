"""The VAT registrations of a company from its record "Malta VAT Registration": the registration under Article 10
or Article 11 on a date, a registration under Article 12 beside it, and the first known day of a registration. A
row without a first day applies from before the books, a row without a last day until further notice.
"""

from datetime import date

import frappe
from frappe.utils import getdate

DOCTYPE = "Malta VAT Registration"
ARTICLE_10 = "Article 10"
ARTICLE_11 = "Article 11"
ARTICLE_12 = "Article 12"
# Registrations that exclude each other on a day.
EXCLUSIVE = ((ARTICLE_10, ARTICLE_11), (ARTICLE_10, ARTICLE_12))


def get(company: str):
	"""The record of the company, or None."""
	return frappe.get_doc(DOCTYPE, company) if frappe.db.exists(DOCTYPE, company) else None


def bounds(row) -> tuple[date, date]:
	"""First and last day of a row, open ends as the earliest and the latest date."""
	return (
		getdate(row.from_date) if row.from_date else date.min,
		getdate(row.to_date) if row.to_date else date.max,
	)


def rows(doc, article: str) -> list:
	return [row for row in doc.registrations if row.article == article]


def row_on(doc, article: str, on: date):
	"""The row of the article that holds the date, or None."""
	for row in rows(doc, article):
		first, last = bounds(row)
		if first <= on <= last:
			return row
	return None


def article_on(doc, on: date) -> str | None:
	"""ARTICLE_10 or ARTICLE_11 for the registration on the date, or None."""
	for article in (ARTICLE_10, ARTICLE_11):
		if row_on(doc, article, on):
			return article
	return None


def overlaps(doc, article: str, first: date, last: date) -> list:
	"""The rows of the article with a day from first to last."""
	return [row for row in rows(doc, article) if bounds(row)[0] <= last and first <= bounds(row)[1]]


def started(doc) -> date | None:
	"""The first day of the earliest registration; None when a row has no first day."""
	firsts = [bounds(row)[0] for row in doc.registrations]
	return None if not firsts or date.min in firsts else min(firsts)


def described(doc, article: str) -> str:
	"""The rows of the article as text, such as "Article 11 (1234-5678) from 2025-01-01"."""
	parts = []
	for row in rows(doc, article):
		text = article + (f" ({row.registration_number})" if row.registration_number else "")
		if row.from_date:
			text += f" from {getdate(row.from_date).isoformat()}"
		if row.to_date:
			text += f" until {getdate(row.to_date).isoformat()}"
		parts.append(text)
	return ", ".join(parts)
