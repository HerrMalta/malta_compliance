// Buttons of a saved Malta VAT Registration: the reports of the registrations it lists, for the current year.
frappe.ui.form.on("Malta VAT Registration", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		const articles = (frm.doc.registrations || []).map((row) => row.article);
		const reports = [
			["Article 10", "VAT Return Malta"],
			["Article 11", "VAT Declaration Article 11 Malta"],
			["Article 12", "VAT Article 12 Malta"],
		];
		for (const [article, report] of reports) {
			if (articles.includes(article)) {
				frm.add_custom_button(__(report), () =>
					frappe.set_route("query-report", report, {
						company: frm.doc.company,
						year: new Date().getFullYear(),
					})
				);
			}
		}
	},
});
