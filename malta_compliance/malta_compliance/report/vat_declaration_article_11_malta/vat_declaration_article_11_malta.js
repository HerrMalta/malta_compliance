// Declaration of a registration under Article 11 for a calendar year, with the tests of the turnover limit and of
// the acquisitions threshold (README, "VAT registrations under Articles 11 and 12").
frappe.query_reports["VAT Declaration Article 11 Malta"] = {
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
		if (data && data.exceeded && column.fieldname === "status") {
			value = `<span class="text-danger">${value}</span>`;
		}
		return value;
	},
};
