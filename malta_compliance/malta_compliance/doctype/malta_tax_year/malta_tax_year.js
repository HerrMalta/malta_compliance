// Buttons of a saved Malta Tax Year: payments from the accounts 3210 and 3220, and the three reports of the record.
frappe.ui.form.on("Malta Tax Year", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		frm.add_custom_button(__("Get Payments from the Books"), () => {
			frm.call("fetch_payments").then((r) => {
				frappe.show_alert(__("{0} payments added", [r.message || 0]));
				frm.reload_doc();
			});
		});
		[
			"Income Tax Computation Malta",
			"Provisional Tax Malta",
			"Social Security Contributions Malta",
		].forEach((report) => {
			frm.add_custom_button(
				__(report),
				() => frappe.set_route("query-report", report, { malta_tax_year: frm.doc.name }),
				__("Reports")
			);
		});
	},
});
