"""Figures of the books for the Maltese tax computations: the trade profit of a company in a calendar year, its
interest income, and the payments booked on the accounts 3210 Income Tax Payments and 3220 Social Security
Contributions of the app's chart. Both payment accounts are equity accounts: tax and the taxpayer's own Class 2
contributions are not expenses of the trade.
"""

import frappe
from frappe.utils import flt, getdate

# Account numbers of the chart of the app (setup/chart_self_employed.json).
INCOME_TAX_PAYMENTS = "3210"
CLASS2_PAYMENTS = "3220"
INTEREST_INCOME = "4920"


def _result(interest: bool, company: str, year: int) -> float:
	comparison = "=" if interest else "!="
	rows = frappe.db.sql(
		f"""select sum(gle.credit - gle.debit) from `tabGL Entry` gle join `tabAccount` acc on acc.name = gle.account
		where gle.company = %s and gle.is_cancelled = 0 and gle.posting_date between %s and %s
		and acc.root_type in ('Income', 'Expense') and gle.voucher_type != 'Period Closing Voucher'
		and ifnull(acc.account_number, '') {comparison} %s""",
		(company, getdate(f"{year}-01-01"), getdate(f"{year}-12-31"), INTEREST_INCOME),
	)
	return flt(rows[0][0]) if rows else 0.0


def profit(company: str, year: int) -> float:
	"""Income less expenses of the calendar year, the basis period of an individual (ITA art. 11(1)), without the
	interest income on account 4920 and without the entries of a Period Closing Voucher."""
	return _result(False, company, year)


def interest_income(company: str, year: int) -> float:
	"""Interest income of the calendar year on account 4920: investment income, outside the trade profit and
	outside the earnings of SSA art. 2."""
	return _result(True, company, year)


def payments(companies: list[str], first, last) -> list:
	"""Net debit per voucher and account on the accounts 3210 and 3220 of the companies, posted from first to
	last, in date order."""
	if not companies:
		return []
	return frappe.db.sql(
		"""select gle.posting_date, gle.company, gle.account, acc.account_number, gle.voucher_type, gle.voucher_no,
			sum(gle.debit - gle.credit) as amount, max(gle.remarks) as remarks
		from `tabGL Entry` gle join `tabAccount` acc on acc.name = gle.account
		where gle.company in %s and gle.is_cancelled = 0 and gle.posting_date between %s and %s
			and acc.account_number in %s
		group by gle.posting_date, gle.company, gle.account, acc.account_number, gle.voucher_type, gle.voucher_no
		having sum(gle.debit - gle.credit) > 0
		order by gle.posting_date, gle.voucher_no""",
		(tuple(companies), first, last, (INCOME_TAX_PAYMENTS, CLASS2_PAYMENTS)),
		as_dict=True,
	)
