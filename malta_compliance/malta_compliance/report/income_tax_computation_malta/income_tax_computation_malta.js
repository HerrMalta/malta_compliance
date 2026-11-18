// Income tax computation of a Malta Tax Year record (docs/income-tax.md).
frappe.query_reports["Income Tax Computation Malta"] = {
	filters: [
		{
			fieldname: "malta_tax_year",
			label: __("Malta Tax Year"),
			fieldtype: "Link",
			options: "Malta Tax Year",
			reqd: 1,
		},
	],
};
