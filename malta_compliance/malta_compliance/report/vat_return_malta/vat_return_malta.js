// VAT return of a period in the lines of the tax accountant's worksheet and the boxes of the return form (README,
// "VAT return"), with the creation of the period's settlement entry for Accounts Manager.
(() => {
	const QUARTERS = ["Jan-Mar", "Apr-Jun", "Jul-Sep", "Oct-Dec"];
	const OTHER_DATES = "Other dates";

	// The last quarter that has ended.
	function last_quarter() {
		const today = new Date();
		let index = Math.floor(today.getMonth() / 3) - 1;
		let year = today.getFullYear();
		if (index < 0) {
			index = 3;
			year -= 1;
		}
		return { year, period: QUARTERS[index] };
	}

	function settlement_dialog(report) {
		const filters = report.get_filter_values();
		if (!filters.company || !filters.year || !filters.period) {
			frappe.msgprint(__("Set Company, Year and Period first."));
			return;
		}
		const box42 = (report.data || []).find((row) => row.key === "42");
		const dialog = new frappe.ui.Dialog({
			title: __("Create VAT Settlement"),
			fields: [
				{
					fieldtype: "HTML",
					options: `<p>${__(
						"Creates a draft Journal Entry dated the last day of the period. It clears the VAT accounts 1310, 1320, 2210 and 2220 against 2290 VAT Settlement at the VAT payable as filed; a difference of a few cents to the books goes to the Round Off account."
					)}</p>`,
				},
				{
					fieldname: "filed_payable",
					label: __("VAT Payable as Filed (Box 42)"),
					fieldtype: "Currency",
					reqd: 1,
					default: box42 ? box42.tax : 0,
					description: __("Negative for an excess credit."),
				},
			],
			primary_action_label: __("Create Draft"),
			primary_action(values) {
				frappe.call({
					method: "malta_compliance.vat.settlement.create_settlement",
					args: { filters, filed_payable: values.filed_payable },
					freeze: true,
					callback(r) {
						dialog.hide();
						if (r.message) {
							frappe.set_route("Form", "Journal Entry", r.message);
						}
					},
				});
			},
		});
		dialog.show();
	}

	const start = last_quarter();

	frappe.query_reports["VAT Return Malta"] = {
		filters: [
			{
				fieldname: "company",
				label: __("Company"),
				fieldtype: "Link",
				options: "Company",
				reqd: 1,
				default: frappe.defaults.get_user_default("Company"),
			},
			{
				fieldname: "year",
				label: __("Year"),
				fieldtype: "Int",
				reqd: 1,
				default: start.year,
			},
			{
				fieldname: "period",
				label: __("Period"),
				fieldtype: "Select",
				options: [...QUARTERS, OTHER_DATES].join("\n"),
				reqd: 1,
				default: start.period,
			},
			{
				fieldname: "from_date",
				label: __("From Date"),
				fieldtype: "Date",
				depends_on: `eval:doc.period == "${OTHER_DATES}"`,
			},
			{
				fieldname: "to_date",
				label: __("To Date"),
				fieldtype: "Date",
				depends_on: `eval:doc.period == "${OTHER_DATES}"`,
			},
			{
				fieldname: "excess_credit_bf",
				label: __("Excess Credit B/F"),
				fieldtype: "Currency",
				default: 0,
			},
			{
				fieldname: "adjustment_vat_department",
				label: __("Box 40: Adjustment for VAT Department"),
				fieldtype: "Currency",
				default: 0,
			},
			{
				fieldname: "adjustment_registered_person",
				label: __("Box 41: Adjustment for Registered Person"),
				fieldtype: "Currency",
				default: 0,
			},
			{
				fieldname: "show_invoices",
				label: __("Show Invoices"),
				fieldtype: "Check",
				default: 0,
			},
		],
		formatter(value, row, column, data, default_formatter) {
			value = default_formatter(value, row, column, data);
			if (data && data.bold) {
				value = `<b>${value}</b>`;
			}
			return value;
		},
		onload(report) {
			if (frappe.user.has_role("Accounts Manager") || frappe.user.has_role("System Manager")) {
				report.page.add_inner_button(__("Create VAT Settlement"), () => settlement_dialog(report));
			}
		},
	};
})();
