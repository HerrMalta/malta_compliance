// VAT self-charged under Article 12 in a calendar year: the notices of payment with their due dates and payments,
// and the annual declaration (README, "VAT registrations under Articles 11 and 12").
frappe.query_reports["VAT Article 12 Malta"] = {
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
			label: __("Payments as of"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.bold) {
			value = `<b>${value}</b>`;
		}
		return value;
	},
};
