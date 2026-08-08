"""Incremental Yahoo Finance download, CSV persistence, and chart workflow.

Run this module directly to update local CSV history for a list of tickers
and regenerate their candlestick charts. See README.md for usage details.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle

ROOT_DIR = Path(__file__).resolve().parent
SAVE_DIR = ROOT_DIR / "save"
PICS_DIR = ROOT_DIR / "pics"
WORKER_SCRIPT = ROOT_DIR / "_yf_worker.py"

DEFAULT_TICKERS = ["AAPL", "MSFT"]

# Full supervision list (legacy tickers from yahoo_finance_api.py's
# mySupervisionList). To process the full list instead of DEFAULT_TICKERS,
# comment out the DEFAULT_TICKERS line above and uncomment the two lines
# below (or just run: python main.py 2338.HK AAG.DE BIDU ... one-off).
SUPERVISION_LIST = [
    "2338.HK", "AAG.DE", "BIDU", "BMW.DE", "BAYN.DE", "COK.DE", "CSCO",
    "EVD.DE", "FEV.DE", "HAG.F", "IRBT", "JD", "MTX.DE", "N7G.DE", "PRLB",
    "SHL.DE", "SIX2.DE", "SLM", "TCOM", "TUI1.DE", "VOW3.DE",
]
DEFAULT_TICKERS = SUPERVISION_LIST

# _yf_worker.py talks directly to Yahoo Finance's chart API over plain HTTP,
# bypassing yfinance's curl_cffi backend (which has been observed to crash
# natively in some sandboxed/virtualized environments). It still runs in its
# own subprocess so a crash or hang there can never affect main.py itself,
# and a hard timeout guarantees a single bad ticker can't block the rest of
# the run.
DOWNLOAD_TIMEOUT_SECONDS = 30


def download_ticker_data(ticker: str, start: str, end: str, timeout: float = DOWNLOAD_TIMEOUT_SECONDS):
    """Download one ticker's history from Yahoo Finance in an isolated
    subprocess with a hard timeout.

    Returns (data, error). `error` is set (data is None) if the subprocess
    timed out, crashed, or failed; otherwise data is the downloaded
    DataFrame (possibly empty if there was simply nothing new to fetch).
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "download.csv"
        cmd = [sys.executable, str(WORKER_SCRIPT), ticker, start, end, str(output_path)]
        try:
            result = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            return None, TimeoutError(f"download for {ticker} did not respond within {timeout:.0f}s")

        if result.returncode != 0:
            message = result.stderr.strip() or f"worker exited with code {result.returncode}"
            return None, RuntimeError(message)

        if not output_path.exists() or output_path.stat().st_size == 0:
            return pd.DataFrame(), None

        try:
            data = pd.read_csv(output_path, index_col=0, parse_dates=True)
        except Exception as exc:  # noqa: BLE001 - surface any parse error to the caller
            return None, exc

        return data, None


def ensure_directories(today: date) -> Path:
    """Create the save/pics folders (plus a dated pics subfolder) if missing."""
    SAVE_DIR.mkdir(exist_ok=True)
    PICS_DIR.mkdir(exist_ok=True)
    run_folder = PICS_DIR / str(today)
    run_folder.mkdir(exist_ok=True)
    return run_folder


def safe_filename(value: str) -> str:
    """Sanitize a ticker symbol so it can be used as a file name."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "ticker"


def load_existing_history(path: Path) -> pd.DataFrame:
    """Load a ticker's local CSV history, or an empty DataFrame if absent."""
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()

    try:
        existing = pd.read_csv(path, parse_dates=["Date"])
    except Exception as exc:
        print(f"Could not read existing CSV {path.name}: {exc}")
        return pd.DataFrame()

    if existing.empty:
        return pd.DataFrame()

    existing["Date"] = pd.to_datetime(existing["Date"])
    existing = existing.set_index("Date").sort_index()

    if "Adj Close" not in existing.columns and "Close" in existing.columns:
        existing["Adj Close"] = existing["Close"]

    return existing


def normalize_downloaded(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize a raw yfinance download into the standard OHLCV column set."""
    if raw is None or raw.empty:
        return pd.DataFrame()

    data = raw.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]

    data.index = pd.to_datetime(data.index)
    data.index.name = "Date"

    if "Adj Close" not in data.columns and "Close" in data.columns:
        data["Adj Close"] = data["Close"]

    required = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    missing = [col for col in required if col not in data.columns]
    if missing:
        raise ValueError(f"Downloaded data is missing columns: {missing}")

    return data[required].sort_index()


def update_ticker_history(ticker: str, existing: pd.DataFrame, today: date) -> pd.DataFrame:
    """Download only the rows missing since the last stored date and merge them
    into `existing`, de-duplicating by date (newest download wins).
    """
    if existing.empty:
        start = "2020-01-01"
    else:
        last_date = pd.Timestamp(existing.index.max()).normalize()
        start = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")

    end = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    if start >= end:
        return existing

    raw, error = download_ticker_data(ticker, start, end)
    if error is not None:
        print(f"Download failed for {ticker}: {error}")
        return existing

    if raw is None or raw.empty:
        return existing

    try:
        new_rows = normalize_downloaded(raw)
    except ValueError as exc:
        print(f"Unexpected data format for {ticker}: {exc}")
        return existing

    if existing.empty:
        combined = new_rows
    else:
        combined = pd.concat([existing, new_rows]).sort_index()
        combined = combined[~combined.index.duplicated(keep="last")]

    return combined


def fast_analyse(series: pd.Series) -> str:
    """Return a +/- string per rolling-average window indicating trend direction."""
    windows = [2, 5, 15, 25, 50, 200]
    output = []
    for window in windows:
        slope = series.rolling(window=window).mean().diff().dropna()
        output.append("+" if (not slope.empty and slope.iloc[-1] > 0) else "-")
    return "".join(output)


def plot_ticker(data: pd.DataFrame, ticker: str, output_path: Path) -> None:
    """Render a candlestick chart with 20/100-day MAs, limit lines, volume,
    and a trend indicator in the title, and save it to `output_path`.
    """
    if data.empty:
        return

    view = data.tail(400).copy()
    if view.empty:
        return

    dates_num = mdates.date2num(view.index.to_pydatetime())
    ma20 = view["Adj Close"].rolling(window=20).mean()
    ma100 = view["Adj Close"].rolling(window=100).mean()
    trend = fast_analyse(view["Adj Close"])

    fig, (ax1, ax2) = plt.subplots(
        2,
        1,
        figsize=(12, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )

    candle_width = 0.6
    for stamp, row in view.iterrows():
        x = mdates.date2num(stamp)
        open_price = float(row["Open"])
        close_price = float(row["Close"])
        high = float(row["High"])
        low = float(row["Low"])
        color = "g" if close_price >= open_price else "r"

        rect = Rectangle(
            (x - candle_width / 2, min(open_price, close_price)),
            candle_width,
            max(abs(close_price - open_price), 1e-6),
            facecolor=color,
            edgecolor=color,
            alpha=0.7,
        )
        ax1.add_patch(rect)
        ax1.vlines(x, low, high, color=color, linewidth=1)

    ax1.plot(dates_num, ma100.values, color="blue", linewidth=1.3, label="100 MA")
    ax1.plot(dates_num, ma20.values, color="orange", linewidth=1.3, label="20 MA")

    ma100_recent = ma100.dropna().tail(100)
    if not ma100_recent.empty:
        upper = float(ma100_recent.max())
        lower = float(ma100_recent.min())
        ax1.axhline(y=upper, color="g", linestyle="-")
        ax1.axhline(y=lower, color="r", linestyle="-")

    ax1.set_title(f"{ticker} Trend: {trend}")
    ax1.set_ylabel("Price")
    ax1.legend(loc="upper left")

    ax2.fill_between(dates_num, view["Volume"].values, 0, color="gray", alpha=0.4)
    dx = view["Adj Close"] - ma100.rolling(window=50).mean()
    ax2.plot(dates_num, dx.values, color="black", linewidth=1)
    ax2.set_ylabel("Volume / Delta")
    ax2.set_xlabel("Date")

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def process_ticker(ticker: str, run_folder: Path, today: date) -> None:
    """Update local history for one ticker, persist it, and render its chart."""
    csv_path = SAVE_DIR / f"{safe_filename(ticker)}.csv"
    existing = load_existing_history(csv_path)
    before_rows = len(existing)

    combined = update_ticker_history(ticker, existing, today)
    if combined.empty:
        print(f"{ticker}: no data available")
        return

    combined_to_save = combined.reset_index().rename(columns={"index": "Date"})
    combined_to_save.to_csv(csv_path, index=False)

    after_rows = len(combined)
    added_rows = max(after_rows - before_rows, 0)
    print(f"{ticker}: stored rows={after_rows}, added={added_rows}")

    image_path = run_folder / f"{safe_filename(ticker)}_{today}.png"
    plot_ticker(combined, ticker, image_path)
    print(f"{ticker}: chart saved -> {image_path.name}")


def main() -> int:
    """Entry point: process CLI-provided tickers, or DEFAULT_TICKERS if none given."""
    today = date.today()
    run_folder = ensure_directories(today)

    tickers = [t for t in sys.argv[1:] if t.strip()]
    if not tickers:
        tickers = DEFAULT_TICKERS

    print(f"Processing {len(tickers)} tickers: {', '.join(tickers)}")
    for ticker in tickers:
        process_ticker(ticker, run_folder, today)

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
