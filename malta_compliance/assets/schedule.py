"""Asset Depreciation Schedule for assets of a category with a Maltese allowance rule (override_doctype_class); every
other asset runs ERPNext's code. Three methods of ERPNext's DepreciationScheduleController are replaced, and
selfcheck.py verifies after each migration that they still exist and produce the expected rows:

- `_check_is_pro_rata`: no pro-rata first period; the year of first use receives a full year (S.L. 123.01 rule 7(a)).
- `get_depreciation_amount`: a fixed amount per year from first use, independent of booked months.
- `set_depreciation_amount_for_disposal`: no row in the year of disposal (rule 7(b)), except a full row when the
  disposal date is the schedule date of that year's row. Intellectual property receives the full instalment of the
  year of disposal, dated on the disposal: paragraph (m) holds no rule like rule 7(b).
"""

from erpnext.assets.doctype.asset_depreciation_schedule.asset_depreciation_schedule import (
	AssetDepreciationSchedule,
)
from frappe.utils import cint, flt, getdate

from malta_compliance.assets import allowance
from malta_compliance.setup.capital_allowances import INTELLECTUAL_PROPERTY

OVERRIDDEN_METHODS = ("_check_is_pro_rata", "get_depreciation_amount", "set_depreciation_amount_for_disposal")


class MaltaAssetDepreciationSchedule(AssetDepreciationSchedule):
	def _mc_rule(self) -> str | None:
		asset = getattr(self, "asset_doc", None)
		return allowance.asset_rule(asset) if asset else None

	def _check_is_pro_rata(self):
		super()._check_is_pro_rata()
		if self._mc_rule():
			self.has_pro_rata = False

	def get_depreciation_amount(self, row_idx):
		if not self._mc_rule():
			return super().get_depreciation_amount(row_idx)
		terms = allowance.frozen_terms(self.asset_doc)
		year_index = cint(self.opening_number_of_booked_depreciations) + row_idx
		return allowance.annual_amount(
			self.asset_doc, terms, year_index, cint(self.fb_row.total_number_of_depreciations)
		)

	def set_depreciation_amount_for_disposal(self, row_idx):
		rule = self._mc_rule()
		if not rule:
			return super().set_depreciation_amount_for_disposal(row_idx)
		if rule != INTELLECTUAL_PROPERTY and getdate(self.schedule_date) != getdate(self.disposal_date):
			return
		remaining = flt(self.pending_depreciation_amount) - flt(self.fb_row.expected_value_after_useful_life)
		self.depreciation_amount = flt(
			min(self.depreciation_amount, remaining), self.asset_doc.precision("net_purchase_amount")
		)
		if self.depreciation_amount > 0:
			self.schedule_date = self.disposal_date
			self.add_depr_schedule_row(row_idx)
