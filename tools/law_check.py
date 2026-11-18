"""Compares the consolidated Maltese texts behind the capital allowance rules (malta_compliance/assets/rules.py) with
the versions recorded in malta_compliance/assets/law_versions.json: the version date in the ELI path of
legislation.mt and the SHA-256 of the consolidated PDF. The version path alone does not suffice; S.L. 123.01 keeps
the version 2010-07-22 although it holds an amendment of 2018. Standard library only, no Frappe.

    python tools/law_check.py            exit code 1 and a Markdown summary on stdout when a text changed, 2 on error
    python tools/law_check.py --update   writes the current versions into law_versions.json
"""

import hashlib
import json
import pathlib
import re
import sys
import urllib.request

VERSIONS = (
	pathlib.Path(__file__).resolve().parent.parent / "malta_compliance" / "assets" / "law_versions.json"
)
BASE = "https://legislation.mt"
USER_AGENT = "malta-compliance-law-check (https://github.com/HerrMalta/malta_compliance)"
TEXTS = {
	"eli/cap/123": "Income Tax Act, Cap. 123",
	"eli/sl/123.1": "Deduction for Wear and Tear of Plant and Machinery Rules, S.L. 123.01",
	"eli/sl/123.7": "Income Tax (Deductions) Rules, S.L. 123.07",
	"eli/sl/123.173": "Industrial Buildings and Structures (Capital Allowances) Rules, S.L. 123.173",
	"eli/sl/123.88": "Finance Leasing Rules, S.L. 123.88",
}


def fetch(url: str) -> bytes:
	request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
	with urllib.request.urlopen(request, timeout=120) as response:
		return response.read()


def current(eli: str) -> dict:
	"""Version date and PDF checksum of the current consolidation."""
	page = fetch(f"{BASE}/{eli}/eng").decode("utf-8", "replace")
	version = re.search(rf'about="mlt:{re.escape(eli)}/(\d{{8}})/eng"', page)
	pdf = re.search(r"getpdf/[0-9a-f]+", page)
	if not version or not pdf:
		raise RuntimeError(f"{eli}: version or PDF link not found on {BASE}/{eli}/eng")
	return {
		"version": version.group(1),
		"sha256": hashlib.sha256(fetch(f"{BASE}/{pdf.group(0)}")).hexdigest(),
	}


def main() -> int:
	found = {eli: current(eli) for eli in TEXTS}
	if "--update" in sys.argv:
		VERSIONS.write_text(json.dumps(found, indent=1, sort_keys=True) + "\n", encoding="utf-8")
		return 0
	recorded = json.loads(VERSIONS.read_text(encoding="utf-8"))
	changed = [eli for eli in TEXTS if recorded.get(eli) != found[eli]]
	if not changed:
		return 0
	print(
		"The following consolidated texts on legislation.mt differ from `malta_compliance/assets/law_versions.json`:\n"
	)
	for eli in changed:
		before, after = recorded.get(eli, {}), found[eli]
		print(
			f"- {TEXTS[eli]} ({BASE}/{eli}/eng): version {before.get('version')} -> {after['version']}, "
			f"PDF {str(before.get('sha256'))[:12]} -> {after['sha256'][:12]}"
		)
	print(
		"\nReview the change against docs/capital-allowances.md and malta_compliance/assets/rules.py, then record "
		"the new versions with `python tools/law_check.py --update`."
	)
	return 1


if __name__ == "__main__":
	try:
		sys.exit(main())
	except Exception as e:  # exit code 2 keeps a fetch error apart from a changed text
		print(f"law check failed: {e}", file=sys.stderr)
		sys.exit(2)
