app_name = "malta_compliance"
app_title = "Malta Compliance"
app_publisher = "HerrMalta"
app_description = "Malta tax helpers for ERPNext: VAT return, income tax, provisional tax and social security contributions (SSC)"
app_email = "247870707+HerrMalta@users.noreply.github.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

# The desk entry is the Dock record in dock/malta_compliance/malta_compliance.json, mounted on ERPNext's rail
# (mount_on). Frappe shows no apps-screen tile for a mounted app, so add_to_apps_screen is not declared.

# Icons of the rail entry and the sidebar header.
app_include_icons = ["/assets/malta_compliance/icons/module-icons.svg"]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/malta_compliance/css/malta_compliance.css"
# app_include_js = "/assets/malta_compliance/js/malta_compliance.js"

# include js, css files in header of web template
# web_include_css = "/assets/malta_compliance/css/malta_compliance.css"
# web_include_js = "/assets/malta_compliance/js/malta_compliance.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "malta_compliance/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_kanban_js = {"doctype" : "public/js/doctype_kanban.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "malta_compliance/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "malta_compliance.utils.jinja_methods",
# 	"filters": "malta_compliance.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "malta_compliance.install.before_install"
# after_install = "malta_compliance.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "malta_compliance.uninstall.before_uninstall"
# after_uninstall = "malta_compliance.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "malta_compliance.utils.before_app_install"
# after_app_install = "malta_compliance.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "malta_compliance.utils.before_app_uninstall"
# after_app_uninstall = "malta_compliance.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "malta_compliance.build.after_build"

# To hook into the build process of other apps
# The list of apps being built is passed as an argument

# after_app_build = "malta_compliance.build.after_app_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "malta_compliance.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["malta_compliance.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"malta_compliance.tasks.all"
# 	],
# 	"daily": [
# 		"malta_compliance.tasks.daily"
# 	],
# 	"hourly": [
# 		"malta_compliance.tasks.hourly"
# 	],
# 	"weekly": [
# 		"malta_compliance.tasks.weekly"
# 	],
# 	"monthly": [
# 		"malta_compliance.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "malta_compliance.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "malta_compliance.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "malta_compliance.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "malta_compliance.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["malta_compliance.utils.before_request"]
# after_request = ["malta_compliance.utils.after_request"]

# Job Events
# ----------
# before_job = ["malta_compliance.utils.before_job"]
# after_job = ["malta_compliance.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"malta_compliance.auth.validate"
# ]

# on_social_login = "malta_compliance.auth.on_social_login"

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []


# Custom fields of the capital allowances and of the VAT settlement
# -----------------------------------------------------------------

after_install = [
	"malta_compliance.setup.capital_allowances.after_install",
	"malta_compliance.setup.vat.after_install",
]

# Capital allowances (docs/capital-allowances.md)
# -----------------------------------------------

after_migrate = ["malta_compliance.assets.selfcheck.run"]

override_doctype_class = {
	"Asset Depreciation Schedule": "malta_compliance.assets.schedule.MaltaAssetDepreciationSchedule",
}

doc_events = {
	"Asset": {
		"before_validate": "malta_compliance.assets.events.asset_before_validate",
		"validate": "malta_compliance.assets.events.asset_validate",
		"before_update_after_submit": "malta_compliance.assets.events.asset_before_update_after_submit",
	},
	"Journal Entry": {
		"on_submit": "malta_compliance.assets.depreciation.on_journal_entry_submit",
		"before_cancel": "malta_compliance.assets.depreciation.before_journal_entry_cancel",
		"on_cancel": "malta_compliance.assets.depreciation.on_journal_entry_cancel",
	},
	"Sales Invoice": {
		"on_submit": "malta_compliance.assets.balancing.on_sales_invoice_submit",
		"on_cancel": "malta_compliance.assets.balancing.on_sales_invoice_cancel",
	},
	"Asset Value Adjustment": {"validate": "malta_compliance.assets.events.asset_value_adjustment_validate"},
	"Asset Repair": {"validate": "malta_compliance.assets.events.asset_repair_validate"},
	"Asset Capitalization": {"validate": "malta_compliance.assets.events.asset_capitalization_validate"},
}
