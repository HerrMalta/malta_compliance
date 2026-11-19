// Button of a saved Malta Taxpayer: the payments of the current year in the report "Tax Payments Malta".
frappe.ui.form.on("Malta Taxpayer", {
	refresh(frm) {
		if (frm.is_new() || !(frm.doc.companies || []).length) {
			return;
		}
		frm.add_custom_button(__("Tax Payments Malta"), () =>
			frappe.set_route("query-report", "Tax Payments Malta", {
				company: frm.doc.companies[0].company,
				year: new Date().getFullYear(),
			})
		);
	},
});
