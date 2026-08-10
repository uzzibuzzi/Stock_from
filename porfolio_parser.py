"""
HedgeFollow fund-holdings scraper.

hedgefollow.com renders its holdings table client-side via JavaScript, so a
plain `requests.get()` returns an HTML shell with empty <tbody> elements.
This script uses Selenium (headless Chrome) to let the page fully render,
then parses the "Top Holdings" table into a list of Python dicts.

Install requirements:
    pip install selenium

You also need a Chrome/Chromium browser and a matching chromedriver on PATH.
(Selenium Manager, bundled with recent selenium versions, will usually
download the right driver automatically the first time you run this.)

Usage:
    python hedgefollow_scraper.py "Renaissance+Technologies"
    python hedgefollow_scraper.py "Renaissance Technologies"
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


BASE_URL = "https://hedgefollow.com/funds/{}"


@dataclass
class Holding:
    ticker: str
    company_name: str
    pct_of_portfolio: str
    shares_owned: str
    value_owned: str
    latest_activity: str
    sector: str


def build_url(fund_name: str) -> str:
    # HedgeFollow expects spaces as literal "+" in the URL path.
    normalized = fund_name.strip().replace(" ", "+")
    normalized = urllib.parse.quote(normalized, safe="+")
    return BASE_URL.format(normalized)


_EDGE_PATHS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)
_EDGEDRIVER_URL = "https://msedgedriver.microsoft.com/{version}/edgedriver_win64.zip"


def _detect_edge_version() -> str:
    """Return the installed Edge's full version string (e.g. '150.0.4078.105')."""
    for path in _EDGE_PATHS:
        if os.path.exists(path):
            out = subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    f"(Get-Item '{path}').VersionInfo.ProductVersion",
                ],
                capture_output=True, text=True,
            )
            version = out.stdout.strip()
            if version:
                return version
    raise RuntimeError("Microsoft Edge was not found; please install Edge.")


def _curl_download(url: str, dest: Path) -> None:
    """Download ``url`` to ``dest`` using Windows curl.exe.

    curl.exe uses the OS certificate store (so it works behind the corporate
    SSL-interception proxy) and is far more robust than the streaming
    downloader in webdriver-manager, which truncated the driver zip on this
    network.
    """
    subprocess.run(
        ["curl.exe", "-fL", "--retry", "5", "--retry-all-errors",
         "-o", str(dest), url],
        check=True,
    )


def ensure_edgedriver() -> str:
    """Return a path to a msedgedriver.exe matching the installed Edge.

    Resolution order:
      1. ``EDGEDRIVER_PATH`` env var, if it points at an existing file.
      2. A cached driver under ``~/.edgedriver/<version>/``.
      3. Download the matching driver with curl.exe.

    Edge is used instead of Chrome because corporate policy sets
    ``RemoteDebuggingAllowed = 0`` for Chrome, which blocks Selenium from
    attaching to it ("DevTools remote debugging is disallowed by the system
    admin"). Selenium Manager and webdriver-manager are avoided for the
    reasons documented on the download helper.
    """
    env_path = os.environ.get("EDGEDRIVER_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    version = _detect_edge_version()
    cache_dir = Path.home() / ".edgedriver" / version
    driver_path = cache_dir / "msedgedriver.exe"
    if driver_path.exists():
        return str(driver_path)

    cache_dir.mkdir(parents=True, exist_ok=True)
    zip_path = cache_dir / "edgedriver_win64.zip"
    _curl_download(_EDGEDRIVER_URL.format(version=version), zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(cache_dir)
    if not driver_path.exists():
        raise RuntimeError("msedgedriver.exe was not found after extraction.")
    return str(driver_path)


def get_driver(headless: bool = True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,2000")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    service = Service(ensure_edgedriver())
    return webdriver.Edge(service=service, options=options)


def find_holdings_table(driver):
    """
    Locate the equities 'Top Holdings' table.

    The table has a stable id (``fund_holdings_equities``); we target that
    first. As a fallback we match by header text using ``textContent`` rather
    than ``.text`` — in headless mode the table is off-screen and Selenium's
    ``.text`` (visible text only) returns an empty string, which is why the
    old header match silently failed.
    """
    try:
        return driver.find_element(By.ID, "fund_holdings_equities")
    except Exception:
        pass

    for table in driver.find_elements(By.TAG_NAME, "table"):
        header_text = table.get_attribute("textContent") or ""
        if "Stock" in header_text and "Company Name" in header_text:
            return table
    return None


def _visible_headers(table) -> list[str]:
    """Return the labels of the table's visible columns, in order.

    HedgeFollow hides several columns (e.g. Sector, Trade Value) with
    ``display: none``; the body rows only contain cells for the visible
    columns. Skipping the hidden headers keeps header labels aligned with the
    cells actually present in each row.
    """
    headers = []
    for th in table.find_elements(By.CSS_SELECTOR, "thead th"):
        if th.value_of_css_property("display") == "none":
            continue
        headers.append((th.get_attribute("textContent") or "").strip())
    return headers


def parse_table(table) -> list[Holding]:
    headers = _visible_headers(table)
    holdings = []
    for row in table.find_elements(By.CSS_SELECTOR, "tbody tr"):
        # Use textContent: cell .text is empty when the table is off-screen
        # in headless mode.
        cells = [
            (c.get_attribute("textContent") or "").strip()
            for c in row.find_elements(By.TAG_NAME, "td")
        ]
        if not cells:
            continue

        # Prefer mapping cells to header labels by name (robust to column
        # reordering); fall back to fixed positions if counts don't line up.
        record = dict(zip(headers, cells)) if len(headers) == len(cells) else {}

        def col(name: str, idx: int) -> str:
            if name in record:
                return record[name]
            return cells[idx] if idx < len(cells) else ""

        ticker = col("Stock", 0)
        company_name = col("Company Name", 1)
        pct_of_portfolio = col("% of Portfolio", 2)
        # Skip non-holding rows (e.g. injected ad / spacer rows), which lack a
        # company name and portfolio percentage.
        if not company_name or not pct_of_portfolio:
            continue

        holdings.append(
            Holding(
                ticker=ticker,
                company_name=company_name,
                pct_of_portfolio=pct_of_portfolio,
                shares_owned=col("Shares Owned", 3),
                value_owned=col("Value Owned", 4),
                latest_activity=col("Latest Activity", 5),
                # Sector is a hidden column on the site, so it is usually blank.
                sector=record.get("Sector", ""),
            )
        )
    return holdings


def scrape_fund_holdings(fund_name: str, headless: bool = True, wait_seconds: int = 15):
    url = build_url(fund_name)
    driver = get_driver(headless=headless)
    try:
        driver.get(url)

        # Wait for the equities holdings table to be populated (its rows are
        # filled in by JS after the initial HTML loads).
        WebDriverWait(driver, wait_seconds).until(
            lambda d: len(
                d.find_elements(
                    By.CSS_SELECTOR, "#fund_holdings_equities tbody tr"
                )
            )
            > 0
        )
        # Small extra buffer for the table to finish rendering all rows.
        time.sleep(1.5)

        table = find_holdings_table(driver)
        if table is None:
            raise RuntimeError("Could not locate the holdings table on the page.")

        holdings = parse_table(table)
        return holdings
    finally:
        driver.quit()


if __name__ == "__main__":
    fund = sys.argv[1] if len(sys.argv) > 1 else "Renaissance+Technologies"
    print(f"Scraping holdings for: {fund} ...")

    holdings = scrape_fund_holdings(fund)

    # Convert to a plain list of dicts, i.e. the "Python list" requested.
    holdings_list = [asdict(h) for h in holdings]

    print(f"\nFound {len(holdings_list)} holdings.\n")
    for h in holdings_list[:10]:
        print(h)

    if len(holdings_list) > 10:
        print(f"... and {len(holdings_list) - 10} more.")