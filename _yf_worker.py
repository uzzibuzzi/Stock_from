"""Standalone worker process: downloads OHLCV data for one ticker directly
from the Yahoo Finance chart API and writes it to a CSV file.

This talks to Yahoo Finance directly over plain HTTP (via urllib) instead of
going through yfinance's `curl_cffi` HTTP backend, which has been observed to
crash natively in some sandboxed/virtualized environments. main.py still runs
this in its own subprocess so a crash or hang here can never affect the main
script, and a hard timeout guarantees a single bad ticker can't block the
rest of a run.

Usage: python _yf_worker.py <ticker> <start> <end> <output_csv_path>
Exits 0 on success (CSV written; an empty file means "no data available").
Exits non-zero on failure, with a message printed to stderr.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytz

CHART_API_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _http_get(url: str, timeout: float) -> bytes:
    """Fetch `url` and return the raw response body.

    Tries Python's urllib first. On networks where Python's bundled OpenSSL
    can't complete the TLS handshake (e.g. corporate TLS-inspection proxies
    like Zscaler, which surface as an ``[ASN1: NOT_ENOUGH_DATA]`` error),
    falls back to the system ``curl`` executable, which on Windows uses the
    native Schannel TLS stack and the OS certificate store.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError:
        # A real HTTP status error (404, etc.) is meaningful - don't mask it
        # by retrying with curl.
        raise
    except Exception:
        curl_path = shutil.which("curl")
        if not curl_path:
            raise
        result = subprocess.run(
            [
                curl_path,
                "-s",
                "-S",
                "-f",
                "-m",
                str(int(timeout)),
                "-A",
                USER_AGENT,
                url,
            ],
            capture_output=True,
            timeout=timeout + 5,
        )
        if result.returncode != 0:
            message = result.stderr.decode(errors="replace").strip() or f"curl exited with {result.returncode}"
            raise RuntimeError(message)
        return result.stdout


def fetch_chart_data(ticker: str, start: str, end: str, timeout: float = 20.0) -> pd.DataFrame:
    """Fetch daily OHLCV history for `ticker` between `start` and `end`
    (YYYY-MM-DD, end exclusive) directly from Yahoo Finance's chart API.
    """
    period1 = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    period2 = int(datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())

    params = {
        "period1": period1,
        "period2": period2,
        "interval": "1d",
        "includeAdjustedClose": "true",
    }
    url = f"{CHART_API_URL.format(symbol=urllib.parse.quote(ticker))}?{urllib.parse.urlencode(params)}"

    payload = json.loads(_http_get(url, timeout))

    chart = payload.get("chart", {})
    if chart.get("error"):
        raise RuntimeError(str(chart["error"]))

    results = chart.get("result") or []
    if not results:
        return pd.DataFrame()

    result = results[0]
    timestamps = result.get("timestamp") or []
    if not timestamps:
        return pd.DataFrame()

    quote = result["indicators"]["quote"][0]
    adjclose_list = result["indicators"].get("adjclose")
    adjclose = adjclose_list[0]["adjclose"] if adjclose_list else quote["close"]

    tz_name = result.get("meta", {}).get("exchangeTimezoneName") or "America/New_York"
    index = pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(pytz.timezone(tz_name)).tz_localize(None).normalize()

    data = pd.DataFrame(
        {
            "Open": quote["open"],
            "High": quote["high"],
            "Low": quote["low"],
            "Close": quote["close"],
            "Adj Close": adjclose,
            "Volume": quote["volume"],
        },
        index=index,
    )
    data.index.name = "Date"
    data = data.dropna(subset=["Close"])
    return data.sort_index()


def main() -> int:
    if len(sys.argv) != 5:
        print("usage: _yf_worker.py <ticker> <start> <end> <output_csv_path>", file=sys.stderr)
        return 2

    ticker, start, end, output_arg = sys.argv[1:5]
    output_path = Path(output_arg)

    try:
        data = fetch_chart_data(ticker, start, end)
    except urllib.error.HTTPError as exc:
        print(f"download error: HTTP {exc.code} {exc.reason}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - report any download error to the parent process
        print(f"download error: {exc}", file=sys.stderr)
        return 1

    if data.empty:
        output_path.write_text("")
        return 0

    data.to_csv(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
