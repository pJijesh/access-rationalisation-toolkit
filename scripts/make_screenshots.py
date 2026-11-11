"""Regenerate the README screenshots from the committed example reports.

Optional developer tool: needs Playwright with Chromium installed
(pip install playwright && playwright install chromium). Not used by the package or its tests.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto((ROOT / "examples/demo-output/report.html").as_uri())
    page.screenshot(path=str(ROOT / "docs/report-overview.png"), clip={"x": 0, "y": 0, "width": 1280, "height": 1020})
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto((ROOT / "examples/demo-output-aggressive/report.html").as_uri())
    page.locator("#gains").screenshot(path=str(ROOT / "docs/report-review-list.png"))
    browser.close()
