from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE_PATH = ROOT / "site" / "landskapspotential" / "index.html"
EXPECTED_REGIONS = {"bornholm", "trondelag", "skaraborg"}
ACTIVE_APP_REGIONS = {"trondelag"}
STREAMLIT_APP_URL = "https://speedlocal-landskapspotential.streamlit.app"
LEGACY_APP_LINKS = {
    "https://landskapsanalys-potential-v1.streamlit.app/",
    "https://landskapsanalys-potential-v2-test.streamlit.app/",
}
EXPECTED_BUTTON_TEXT = {
    "V2 Final Tröndelag",
    "V1-referens",
    "Fryst V2",
}


class LandingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self.region_cards: set[str] = set()
        self.hrefs: list[str] = []
        self.app_routes: set[str] = set()
        self.link_texts: set[str] = set()
        self._current_link_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "title":
            self._in_title = True
        if tag == "article" and values.get("data-region"):
            self.region_cards.add(values["data-region"])
        if tag == "a":
            self.hrefs.append(values.get("href", ""))
            self._current_link_parts = []
            if values.get("data-app-route"):
                self.app_routes.add(values["data-app-route"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._current_link_parts is not None:
            text = " ".join("".join(self._current_link_parts).split())
            if text:
                self.link_texts.add(text)
            self._current_link_parts = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._current_link_parts is not None:
            self._current_link_parts.append(data)


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
    expected_routes = {f"?region={region}" for region in ACTIVE_APP_REGIONS}
    if parser.app_routes != expected_routes:
        failures.append(f"App route placeholders mismatch: {sorted(parser.app_routes)}")
    expected_links = {f"{STREAMLIT_APP_URL}/?region={region}" for region in ACTIVE_APP_REGIONS}
    missing_links = expected_links.difference(parser.hrefs)
    if missing_links:
        failures.append(f"Missing Streamlit deep links: {sorted(missing_links)}")
    disabled_region_links = {
        region: f"{STREAMLIT_APP_URL}/?region={region}"
        for region in ("bornholm", "skaraborg")
    }
    exposed_disabled_links = {
        region: href
        for region, href in disabled_region_links.items()
        if href in parser.hrefs
    }
    if exposed_disabled_links:
        failures.append(
            f"Disabled regions have active app links: {exposed_disabled_links}"
        )
    missing_legacy_links = LEGACY_APP_LINKS.difference(parser.hrefs)
    if missing_legacy_links:
        failures.append(f"Missing legacy V1/V2 app links: {sorted(missing_legacy_links)}")
    missing_button_text = EXPECTED_BUTTON_TEXT.difference(parser.link_texts)
    if missing_button_text:
        failures.append(f"Missing expected button text: {sorted(missing_button_text)}")
    if "/speedlocal/landskapspotential/" not in html:
        failures.append("Canonical Pages path is not documented in landing page.")
    if "V2 Final väntar på validerad data" not in html:
        failures.append("Skaraborg does not show its planned/disabled V2 Final state.")
    if "V2 Final under onboarding" not in html:
        failures.append("Bornholm does not show its onboarding/disabled V2 Final state.")
    if 'const localAppBase = "http://127.0.0.1:8502/";' not in html:
        failures.append("Local landing-page routing does not target V2 Final on port 8502.")
    if 'document.querySelectorAll("[data-app-route]")' not in html:
        failures.append("Local landing-page routing does not update region links.")

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
    print("- PASS Trondelag alone links to active V2 Final with a region query param.")
    print("- PASS App route placeholders are documented as query routes.")
    print("- PASS The Trondelag Streamlit Cloud deep link exists.")
    print("- PASS Bornholm and Skaraborg remain visible without active app links.")
    print("- PASS Existing V1 and V2 app links remain visible.")
    print("- PASS Region buttons use clear open labels.")
    print("- PASS Canonical Pages path is documented.")
    print("- PASS Local landing page routes the Trondelag V2 Final button to port 8502.")
    print("\nRESULT: PASS (11 passed, 0 blocker(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
