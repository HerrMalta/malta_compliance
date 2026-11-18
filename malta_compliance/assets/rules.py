"""Register of the Maltese capital allowance rules applied by the app, each with the period in which it applies and
its legal source (docs/capital-allowances.md). Every period, rate and amount used for an asset comes from here.

A version is selected by the date its rule is keyed to: the date of first use (`available_for_use_date`), the date
of acquisition (`purchase_date`) or a date in the basis year of the claim. Dates are basis-year dates: year of
assessment N belongs to basis year N - 1. A date outside every version raises NotCovered. REVIEWED_UP_TO is the last
year of assessment for which the register was checked against the law; later years produce a warning.
"""

from dataclasses import dataclass
from datetime import date

# Last year of assessment checked against the law.
REVIEWED_UP_TO = 2027

# Start of the regime of S.L. 123.01: basis year of year of assessment 2002.
WEAR_AND_TEAR_START = date(2001, 1, 1)


class NotCovered(Exception):
	"""The date lies outside every version of a rule."""


@dataclass(frozen=True)
class Version:
	"""One version of a rule; valid_to None means open-ended."""

	rule: str
	valid_from: date
	valid_to: date | None
	value: float
	source: str

	@property
	def code(self) -> str:
		return f"{self.rule}@{self.valid_from.isoformat()}"


def _versions(rule: str, *rows: tuple) -> tuple[Version, ...]:
	return tuple(
		Version(rule, valid_from, valid_to, value, source) for valid_from, valid_to, value, source in rows
	)


# Minimum number of years per item of the Schedule to S.L. 123.01, keyed to the date of first use; item 7 is keyed to
# the date of acquisition. Aircraft acquired before 2018 had separate periods for airframes and interiors and are
# not covered.
_SCHEDULE = {
	1: 4,
	2: 4,
	3: 5,
	4: 10,
	5: 6,
	6: 6,
	8: 10,
	9: 15,
	10: 20,
	11: 20,
	12: 6,
	13: 6,
	14: 10,
	15: 6,
	16: 6,
	17: 5,
	18: 10,
}
WEAR_AND_TEAR_YEARS = {
	item: _versions(f"WT{item:02d}", (WEAR_AND_TEAR_START, None, years, f"S.L. 123.01 Schedule item {item}"))
	for item, years in _SCHEDULE.items()
}
WEAR_AND_TEAR_YEARS[7] = _versions(
	"WT07", (date(2018, 1, 1), None, 4, "S.L. 123.01 Schedule item 7 as substituted by L.N. 322 of 2018")
)

# Initial deduction on plant and machinery (art. 14(1)(j)), keyed to the date of first use.
PLANT_INITIAL_RATE = _versions(
	"PMINIT",
	(date(1949, 1, 1), date(2000, 12, 31), 20, "ITA art. 14(1)(j)"),
	(WEAR_AND_TEAR_START, None, 0, "ITA art. 14(1)(j) second proviso; L.N. 12 of 2002"),
)

# Industrial buildings and structures, keyed to the date of first use.
BUILDING_ANNUAL_RATE = _versions("IBANNUAL", (WEAR_AND_TEAR_START, None, 2, "ITA art. 14(1)(f) proviso (i)"))
BUILDING_INITIAL_RATE = _versions("IBINIT", (WEAR_AND_TEAR_START, None, 10, "ITA art. 14(1)(j)"))

# Intellectual property (art. 14(1)(m)), keyed to the date of first use. Covered from the basis year of year of
# assessment 2017, the start of the MTCA clarification.
IP_MINIMUM_YEARS = _versions(
	"IPMIN", (date(2016, 1, 1), None, 3, "ITA art. 14(1)(m) first proviso; MTCA clarification")
)
IP_ONE_YEAR = _versions(
	"IP1Y",
	(date(2023, 1, 1), None, 1, "ITA art. 14(1)(m) second proviso; S.L. 123.07 rule 6 (L.N. 229 of 2024)"),
)

# Cost cap on motor vehicles (S.L. 123.07 rule 3(1)), keyed to the basis year of the claim: each year of assessment
# uses the amount in force for it, also for vehicles acquired earlier (reading of the commencement wording; no
# transitional rule exists). Lm 3,000 converted at 0.4293.
VEHICLE_COST_CAP = _versions(
	"CAP",
	(WEAR_AND_TEAR_START, date(2006, 12, 31), 6988.12, "S.L. 123.07 rule 3(1), L.N. 322 of 2001 (Lm 3,000)"),
	(
		date(2007, 1, 1),
		date(2009, 12, 31),
		7000,
		"L.N. 409 of 2007, from 2008-01-01 (year of assessment 2008)",
	),
	(date(2010, 1, 1), None, 14000, "L.N. 369 of 2009, from year of assessment 2011"),
)


def select(versions: tuple[Version, ...], on: date) -> Version:
	for version in versions:
		if version.valid_from <= on and (version.valid_to is None or on <= version.valid_to):
			return version
	raise NotCovered(f"{versions[0].rule}: no version covers {on.isoformat()}")


def wear_and_tear_years(item: int, first_use: date, acquired: date) -> Version:
	return select(WEAR_AND_TEAR_YEARS[item], acquired if item == 7 else first_use)


def review_warning(basis_year: int) -> str | None:
	"""Warning text when the basis year lies after the last reviewed year of assessment, else None."""
	if basis_year + 1 > REVIEWED_UP_TO:
		return (
			f"The Maltese capital allowance rules of this app were reviewed up to year of assessment "
			f"{REVIEWED_UP_TO}; year of assessment {basis_year + 1} is not yet covered by a review."
		)
	return None
