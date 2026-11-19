// A new Malta Tax Year is filled from its Malta Taxpayer once Taxpayer and Basis Year are set. A saved record has
// buttons for the payments from the accounts 3210 and 3220 and for the reports of the record.
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
	taxpayer(frm) {
		fill_from_taxpayer(frm);
	},
	basis_year(frm) {
		fill_from_taxpayer(frm);
	},
});

function fill_from_taxpayer(frm) {
	if (!frm.is_new() || !frm.doc.taxpayer || !/^\d{4}$/.test(frm.doc.basis_year || "")) {
		return;
	}
	frappe
		.call({
			method: "malta_compliance.malta_compliance.doctype.malta_tax_year.malta_tax_year.taxpayer_defaults",
			args: { taxpayer: frm.doc.taxpayer, basis_year: frm.doc.basis_year },
		})
		.then((r) => {
			const values = r.message || {};
			for (const table of ["companies", "items"]) {
				frm.clear_table(table);
				(values[table] || []).forEach((row) => frm.add_child(table, row));
				delete values[table];
			}
			frm.set_value(values);
			frm.refresh_fields();
		});
}
