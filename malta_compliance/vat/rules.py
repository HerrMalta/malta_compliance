"""Register of the Maltese rules on registrations under Articles 11 and 12 of the Value Added Tax Act applied by the
app, each with the period in which it applies and its source (docs/vat-articles-11-12.md): the turnover limits of a
small enterprise, the acquisitions threshold, the dates from which an operation requires a registration under
Article 12, the due date of the declarations, the interest on late payment and the penalty for a late declaration.
A date outside every version raises NotCovered. REVIEWED_UP_TO is the last calendar year checked against the
sources; later years produce a warning. No Frappe imports.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from malta_compliance.tax.rules import MonthlyRate, NotCovered, monthly_rate

# Last calendar year checked against the sources.
REVIEWED_UP_TO = 2026

# Activity categories of the Sixth Schedule until 2024.
GOODS = "Supply of goods"
LOW_VALUE_SERVICES = "Services with a low value added"
OTHER = "Other activities"
ACTIVITIES = (GOODS, LOW_VALUE_SERVICES, OTHER)

# Period over which the turnover of a small enterprise is measured.
RELEVANT_PERIOD = "relevant period"  # twelve months ending on the last day of the preceding calendar quarter
CALENDAR_YEAR = "calendar year"

EUR = "EUR"
MTL = "MTL"
# Maltese liri per euro, the irrevocable conversion rate of Council Regulation (EC) No 1134/2007.
MTL_PER_EUR = Decimal("0.4293")


@dataclass(frozen=True)
class SmallEnterprise:
	"""Turnover limits of a small enterprise (VAT Act art. 11, Sixth Schedule) for the dates first to last; last None
	means open-ended. entry and stay hold, in the order of ACTIVITIES, the limit of an application and the limit of
	a registered person, in whole units of the currency. With entry_below or stay_below the turnover has to be below
	the limit, otherwise not above it. domestic: only supplies taking place in Malta count as turnover."""

	first: date
	last: date | None
	currency: str
	entry: tuple[int, int, int]
	entry_below: bool
	stay: tuple[int, int, int]
	stay_below: bool
	period: str
	domestic: bool
	source: str

	def entry_limit(self, activity: str) -> int:
		"""Limit of an application for the activity, in cents of a euro."""
		return in_cents(self.entry[ACTIVITIES.index(activity)], self.currency)

	def stay_limit(self, activity: str) -> int:
		"""Limit of a registered person for the activity, in cents of a euro."""
		return in_cents(self.stay[ACTIVITIES.index(activity)], self.currency)


@dataclass(frozen=True)
class LatePenalty:
	"""Administrative penalty for a declaration furnished late, for the dates first to last: an amount in euro for
	every month or part of a month of delay, up to a maximum per declaration."""

	first: date
	last: date | None
	per_month: int
	maximum: int
	source: str


_SIXTH = "VAT Act, Sixth Schedule"
_LIRI = (15000, 10000, 6000)
_EURO_2008 = (35000, 24000, 14000)
_EURO_2018 = (35000, 24000, 20000)
_EURO_2021 = (35000, 30000, 30000)
_EURO_2025 = (35000, 35000, 35000)

# Until 2004-04-30 a person became an exempt person below the lower amounts and lost the status from the higher
# ones. The start of the rules of Act X of 2003 lies between 2004-01-01 and 2004-05-01; the register applies
# 2004-05-01 (docs/vat-articles-11-12.md, "Readings").
SMALL_ENTERPRISES = (
	SmallEnterprise(
		date(1999, 1, 1),
		date(2004, 4, 30),
		MTL,
		(12000, 8000, 5000),
		True,
		_LIRI,
		True,
		RELEVANT_PERIOD,
		False,
		f"{_SIXTH}, items 1, 5 and 10 and Table (Act XXIII of 1998)",
	),
	SmallEnterprise(
		date(2004, 5, 1),
		date(2007, 4, 26),
		MTL,
		_LIRI,
		True,
		(12000, 8000, 5000),
		False,
		RELEVANT_PERIOD,
		False,
		f"{_SIXTH}, Part One items 1, 3 and 7 (Act X of 2003)",
	),
	SmallEnterprise(
		date(2007, 4, 27),
		date(2007, 12, 31),
		MTL,
		_LIRI,
		True,
		_LIRI,
		False,
		RELEVANT_PERIOD,
		False,
		f"{_SIXTH}, Part One item 3 (L.N. 122 of 2007)",
	),
	SmallEnterprise(
		date(2008, 1, 1),
		date(2018, 6, 30),
		EUR,
		_EURO_2008,
		True,
		_EURO_2008,
		False,
		RELEVANT_PERIOD,
		False,
		f"{_SIXTH}, Part One Table (L.N. 426 of 2007, L.N. 105 of 2008)",
	),
	SmallEnterprise(
		date(2018, 7, 1),
		date(2020, 12, 31),
		EUR,
		_EURO_2018,
		True,
		_EURO_2018,
		False,
		RELEVANT_PERIOD,
		False,
		f"{_SIXTH}, Part One Table (L.N. 163 of 2018)",
	),
	SmallEnterprise(
		date(2021, 1, 1),
		date(2021, 6, 30),
		EUR,
		_EURO_2008,
		True,
		_EURO_2008,
		False,
		RELEVANT_PERIOD,
		False,
		f"{_SIXTH}, Part One Table (L.N. 163 of 2018 reg. 1(3): its amounts applied until 2020-12-31)",
	),
	SmallEnterprise(
		date(2021, 7, 1),
		date(2024, 12, 31),
		EUR,
		_EURO_2021,
		True,
		_EURO_2021,
		False,
		RELEVANT_PERIOD,
		False,
		f"{_SIXTH}, Part One Table (L.N. 463 of 2020 reg. 3, L.N. 222 of 2021)",
	),
	SmallEnterprise(
		date(2025, 1, 1),
		None,
		EUR,
		_EURO_2025,
		False,
		_EURO_2025,
		False,
		CALENDAR_YEAR,
		True,
		f"{_SIXTH}, definitions 4 and 5 and Part One items 1 and 3 (L.N. 346 of 2024)",
	),
)

# Calendar years in which a person with a turnover of at most the amount in euro was not registered under
# Article 11 and issued no fiscal receipts (L.N. 524 of 2010, revoked by L.N. 67 of 2015).
NO_REGISTRATION_YEARS = (2011, 2014)
NO_REGISTRATION_LIMIT = 7000
NO_REGISTRATION_SOURCE = "L.N. 524 of 2010 reg. 2 and 3, revoked by L.N. 67 of 2015"

# Value in euro of the intra-community acquisitions of goods of a calendar year above which a person not
# registered under Article 10 registers under Article 12 (art. 12(1); Third Schedule Part Three item 3).
ACQUISITIONS_THRESHOLD = 10000
ACQUISITIONS_SOURCE = "VAT Act art. 12(1), Third Schedule Part Three items 3 and 4"

# First day on which an operation requires a registration under Article 12: an intra-community acquisition of
# goods (art. 4(b), accession date), a service whose VAT the customer pays (art. 12(3), Act II of 2009), and a
# service supplied in another Member State whose VAT the customer pays (art. 12(3a), Act XXXVIII of 2024).
ARTICLE_12_GOODS_FROM = date(2004, 5, 1)
ARTICLE_12_SERVICES_RECEIVED_FROM = date(2010, 1, 1)
ARTICLE_12_SERVICES_SUPPLIED_FROM = date(2025, 1, 1)

# Month and day in the following year shown by the MTCA portal as the due date of the declaration of a calendar
# year, for the Article 11 declaration and the annual declaration of Article 12. The Sixth Schedule (Part One
# item 5(5)) names the 15th day of the second month after the period for the Article 11 declaration.
DECLARATION_DUE = (3, 15)

# Day of the month on which self-charged VAT is payable (art. 21(2) and (3)).
PAYMENT_DAY = 15

# Interest on VAT not paid by its due date, for each month or part of a month (art. 21(4)), keyed to the date the
# tax became payable.
VAT_INTEREST = (
	MonthlyRate(date(1999, 1, 1), date(2013, 12, 31), Decimal("1"), "VAT Act art. 21(4)"),
	MonthlyRate(date(2014, 1, 1), date(2019, 12, 31), Decimal("0.54"), "S.L. 406.19 (L.N. 52 of 2014)"),
	MonthlyRate(date(2020, 1, 1), date(2022, 8, 31), Decimal("0.33"), "S.L. 406.19 (L.N. 303 of 2019)"),
	MonthlyRate(date(2022, 9, 1), None, Decimal("0.6"), "S.L. 406.19 (L.N. 227 of 2022)"),
)

# Dates before 2008 are not covered: the amounts were in Maltese liri and their maximum dates from Act XIII of 2005.
LATE_DECLARATION = (
	LatePenalty(
		date(2008, 1, 1), date(2023, 4, 3), 23, 580, "VAT Act art. 38(2) (L.N. 426 of 2007, L.N. 105 of 2008)"
	),
	LatePenalty(
		date(2023, 4, 4), None, 10, 120, "VAT Act art. 38(2)(a) (Act XII of 2023, Act XXXVIII of 2024)"
	),
)


def in_cents(amount: int, currency: str) -> int:
	"""An amount of the register in cents of a euro; Maltese liri at the irrevocable conversion rate."""
	if currency == EUR:
		return amount * 100
	return int((Decimal(amount) / MTL_PER_EUR * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def small_enterprise(on: date) -> SmallEnterprise:
	"""The limits in force on the date."""
	for version in SMALL_ENTERPRISES:
		if version.first <= on and (version.last is None or on <= version.last):
			return version
	raise NotCovered(f"No small-enterprise limit covers {on.isoformat()}")


def exceeds(turnover: int, limit: int, below: bool) -> bool:
	"""True when a turnover is outside a limit: at or above it where the turnover has to be below the limit."""
	return turnover >= limit if below else turnover > limit


def declaration_due(year: int) -> date:
	"""Due date of the declaration of a calendar year."""
	return date(year + 1, *DECLARATION_DUE)


def interest(on: date) -> MonthlyRate:
	"""The monthly interest rate on VAT that became payable on the date."""
	return monthly_rate(VAT_INTEREST, on)


def late_declaration(on: date) -> LatePenalty:
	"""The penalty for a declaration due on the date and furnished late."""
	for version in LATE_DECLARATION:
		if version.first <= on and (version.last is None or on <= version.last):
			return version
	raise NotCovered(f"No penalty for a late declaration covers {on.isoformat()}")


def review_warning(year: int) -> str | None:
	"""Warning text when the year lies after the last reviewed year, else None."""
	if year > REVIEWED_UP_TO:
		return (
			f"The Maltese rules on registrations under Articles 11 and 12 of this app were reviewed up to "
			f"{REVIEWED_UP_TO}; {year} is not yet covered by a review."
		)
	return None
