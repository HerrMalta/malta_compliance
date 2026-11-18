// Class 2 contributions of a Malta Tax Year record (docs/income-tax.md).
frappe.query_reports["Social Security Contributions Malta"] = {
	filters: [
		{
			fieldname: "malta_tax_year",
			label: __("Malta Tax Year"),
			fieldtype: "Link",
			options: "Malta Tax Year",
			reqd: 1,
		},
		{
			fieldname: "as_of",
			label: __("Late Additions as of"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
};
