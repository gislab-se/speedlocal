from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE_PATH = ROOT / "site" / "landskapspotential" / "index.html"
EXPECTED_REGIONS = {"bornholm", "trondelag", "skaraborg"}
STREAMLIT_APP_URL = "https://speedlocal-landskapspotential.streamlit.app"


class LandingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self.region_cards: set[str] = set()
        self.hrefs: list[str] = []
        self.app_routes: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "title":
            self._in_title = True
        if tag == "article" and values.get("data-region"):
            self.region_cards.add(values["data-region"])
        if tag == "a":
            self.hrefs.append(values.get("href", ""))
            if values.get("data-app-route"):
                self.app_routes.add(values["data-app-route"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def main() -> int:
    html = SITE_PATH.read_text(encoding="utf-8")
    parser = LandingParser()
    parser.feed(html)

    failures: list[str] = []
    if "SpeedLocal" not in parser.title:
        failures.append("Missing SpeedLocal title.")
    if parser.region_cards != EXPECTED_REGIONS:
        failures.append(f"Region cards mismatch: {sorted(parser.region_cards)}")
    if any(href.startswith("../") for href in parser.hrefs):
        failures.append(f"Landing page has parent-directory links: {parser.hrefs}")
    expected_routes = {f"?region={region}" for region in EXPECTED_REGIONS}
    if parser.app_routes != expected_routes:
        failures.append(f"App route placeholders mismatch: {sorted(parser.app_routes)}")
    expected_links = {f"{STREAMLIT_APP_URL}/?region={region}" for region in EXPECTED_REGIONS}
    missing_links = expected_links.difference(parser.hrefs)
    if missing_links:
        failures.append(f"Missing Streamlit deep links: {sorted(missing_links)}")
    if "/speedlocal/landskapspotential/" not in html:
        failures.append("Canonical Pages path is not documented in landing page.")

    print("SpeedLocal static site validation")
    print("=" * 33)
    print("\nBLOCKERS")
    if failures:
        for idx, failure in enumerate(failures, start=1):
            print(f"{idx}. FAIL {failure}")
        return 1
    print("None")
    print("\nCHECKS")
    print("- PASS Landing page title names SpeedLocal.")
    print("- PASS Bornholm, Trondelag and Skaraborg cards exist.")
    print("- PASS Card links target the Streamlit Cloud app with region query params.")
    print("- PASS App route placeholders are documented as query routes.")
    print("- PASS Streamlit Cloud deep links exist for all region cards.")
    print("- PASS Canonical Pages path is documented.")
    print("\nRESULT: PASS (6 passed, 0 blocker(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
