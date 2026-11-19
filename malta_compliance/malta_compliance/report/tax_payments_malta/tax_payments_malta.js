// Payments of income tax, provisional tax and Class 2 contributions due in a year (docs/income-tax.md).
frappe.query_reports["Tax Payments Malta"] = {
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
			default: new Date().getFullYear(),
		},
		{
			fieldname: "as_of",
			label: __("Late Additions as of"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
};
