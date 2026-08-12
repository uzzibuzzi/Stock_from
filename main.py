"""Incremental Yahoo Finance download, CSV persistence, and chart workflow.

Run this module directly to update local CSV history for a list of tickers
and regenerate their candlestick charts. See README.md for usage details.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import openpyxl
import pandas as pd
from matplotlib.patches import Rectangle

ROOT_DIR = Path(__file__).resolve().parent
SAVE_DIR = ROOT_DIR / "save"
PICS_DIR = ROOT_DIR / "pics"
WORKER_SCRIPT = ROOT_DIR / "_yf_worker.py"

DEFAULT_LIST = ["AAPL", "MSFT"]

# Full supervision list (legacy tickers from yahoo_finance_api.py's
# mySupervisionList). To process the full list instead of DEFAULT_TICKERS,
# comment out the DEFAULT_TICKERS line above and uncomment the two lines
# below (or just run: python main.py 2338.HK AAG.DE BIDU ... one-off).
SUPERVISION_LIST = [
    "2338.HK", "AAG.DE", "BIDU", "BMW.DE", "BAYN.DE", "COK.DE", "CSCO",
    "EVD.DE", "FEV.DE", "HAG.F", "IRBT", "JD", "MTX.DE", "N7G.DE", "PRLB",
    "SHL.DE", "SIX2.DE", "SLM", "TCOM", "TUI1.DE", "VOW3.DE",
]
DEFAULT_TICKERS = DEFAULT_LIST

# Best-effort mapping from an Aktienfinder.net "Land" (country) column to the
# Yahoo Finance exchange suffix, used by to_yahoo_ticker(). Not guaranteed to
# be correct for every exchange/listing - verify unfamiliar tickers manually.
LAND_TO_SUFFIX = {
    "usa": "",
    "deutschland": ".DE",
    "kanada": ".TO",
    "frankreich": ".PA",
    "niederlande": ".AS",
    "irland": ".DE",
    "daenemark": ".CO",
    "dänemark": ".CO",
    "hong kong": ".HK",
    "china": ".HK",
    "schweiz": ".SW",
    "vereinigtes koenigreich": ".L",
    "vereinigtes königreich": ".L",
    "grossbritannien": ".L",
    "großbritannien": ".L",
    "japan": ".T",
    "spanien": ".MC",
    "italien": ".MI",
    "schweden": ".ST",
    "norwegen": ".OL",
    "belgien": ".BR",
    "oesterreich": ".VI",
    "österreich": ".VI",
}

# Expected trading currency per Yahoo Finance suffix, used to sanity-check
# watchlist buy/sell limits before overlaying them on a chart (Aktienfinder.net
# sometimes displays prices converted to EUR even for non-EUR listings).
SUFFIX_CURRENCY = {
    "": "USD",
    ".DE": "EUR",
    ".PA": "EUR",
    ".AS": "EUR",
    ".TO": "CAD",
    ".HK": "HKD",
    ".CO": "DKK",
    ".SW": "CHF",
    ".L": "GBP",
    ".T": "JPY",
    ".MC": "EUR",
    ".MI": "EUR",
    ".ST": "SEK",
    ".OL": "NOK",
    ".BR": "EUR",
    ".VI": "EUR",
}

# Column names (case-insensitive) checked in order for the ticker source when
# importing a watchlist .xlsx file.
TICKER_COLUMN_CANDIDATES = ["symbol", "ticker", "wkn", "isin"]

# _yf_worker.py talks directly to Yahoo Finance's chart API over plain HTTP,
# bypassing yfinance's curl_cffi backend (which has been observed to crash
# natively in some sandboxed/virtualized environments). It still runs in its
# own subprocess so a crash or hang there can never affect main.py itself,
# and a hard timeout guarantees a single bad ticker can't block the rest of
# the run.
DOWNLOAD_TIMEOUT_SECONDS = 30


def _normalize_stock_list_choice(value: str) -> str:
    """Normalize user-provided --stock-list values to canonical names."""
    normalized = value.strip().lower()
    mapping = {
        "default_list": "DEFAULT_LIST",
        "default": "DEFAULT_LIST",
        "supervision_list": "SUPERVISION_LIST",
        "supervision": "SUPERVISION_LIST",
        "aktienfinder": "Aktienfinder",
    }
    choice = mapping.get(normalized)
    if choice is None:
        options = "DEFAULT_LIST, SUPERVISION_LIST, Aktienfinder"
        raise argparse.ArgumentTypeError(f"invalid stock list '{value}' (choose one of: {options})")
    return choice


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


def to_yahoo_ticker(symbol: str, land: Optional[str]) -> str:
    """Best-effort conversion of an Aktienfinder.net symbol + country into a
    Yahoo Finance ticker (e.g. '02020' + 'Hong Kong' -> '2020.HK',
    'SAP' + 'Deutschland' -> 'SAP.DE', 'NOVO B' + 'D\u00e4nemark' -> 'NOVO-B.CO').
    Not guaranteed to be correct for every exchange - verify unfamiliar
    tickers manually before relying on the downloaded data.
    """
    symbol = symbol.strip()
    if symbol.isdigit():
        return f"{int(symbol):04d}.HK"

    normalized = symbol.replace(" ", "-")
    suffix = LAND_TO_SUFFIX.get((land or "").strip().lower(), "")
    return f"{normalized}{suffix}"


def _expected_currency(ticker: str) -> str:
    """Return the trading currency expected for a Yahoo ticker's exchange suffix."""
    for suffix, currency in SUFFIX_CURRENCY.items():
        if suffix and ticker.endswith(suffix):
            return currency
    return "USD"


def _parse_limit(value: object) -> Tuple[Optional[float], Optional[str]]:
    """Parse a watchlist limit cell like '133.00 USD' into (133.0, 'USD')."""
    if value is None:
        return None, None

    text = str(value).strip()
    if not text:
        return None, None

    match = re.match(r"^([\d.,]+)\s*([A-Za-z]{2,4})?$", text)
    if not match:
        return None, None

    number_text, currency = match.groups()
    try:
        number = float(number_text.replace(",", ""))
    except ValueError:
        return None, None

    return number, currency


def load_watchlist_from_xlsx(path: str, sheet: object = 0) -> list[dict]:
    """Load a watchlist from an Aktienfinder.net-style .xlsx export.

    Looks up the ticker from a 'Symbol' column (falling back to 'Ticker',
    'WKN', or 'ISIN' if present), converts it to a best-effort Yahoo Finance
    ticker using the 'Land' (country) column via to_yahoo_ticker(), and also
    extracts the 'Kauf Limit' / 'Verk. Limit' (buy/sell target price)
    columns if present. Returns a list of dicts, one per watchlist row.
    """
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    worksheet = workbook.worksheets[sheet] if isinstance(sheet, int) else workbook[sheet]

    rows = worksheet.iter_rows(values_only=True)
    header = next(rows, None)
    if header is None:
        raise ValueError(f"{path}: sheet is empty")

    columns = {str(name).strip().lower(): i for i, name in enumerate(header) if name}

    ticker_col = next((columns[c] for c in TICKER_COLUMN_CANDIDATES if c in columns), None)
    if ticker_col is None:
        raise ValueError(
            f"{path}: no ticker column found (looked for {TICKER_COLUMN_CANDIDATES}); "
            f"available columns: {list(columns.keys())}"
        )

    land_col = columns.get("land")
    isin_col = columns.get("isin")
    name_col = columns.get("aktie", columns.get("name"))
    buy_col = columns.get("kauf limit")
    sell_col = columns.get("verk. limit")

    def cell(row: tuple, col: Optional[int]):
        return row[col] if col is not None and col < len(row) else None

    entries = []
    seen: set[str] = set()
    for row in rows:
        if row is None:
            continue
        raw_symbol = cell(row, ticker_col)
        if raw_symbol is None or not str(raw_symbol).strip():
            continue

        land = cell(row, land_col)
        ticker = to_yahoo_ticker(str(raw_symbol), land)
        if ticker in seen:
            continue
        seen.add(ticker)

        buy_limit, buy_currency = _parse_limit(cell(row, buy_col))
        sell_limit, sell_currency = _parse_limit(cell(row, sell_col))

        entries.append(
            {
                "ticker": ticker,
                "symbol": str(raw_symbol).strip(),
                "isin": cell(row, isin_col),
                "name": cell(row, name_col),
                "land": land,
                "buy_limit": buy_limit,
                "buy_currency": buy_currency,
                "sell_limit": sell_limit,
                "sell_currency": sell_currency,
            }
        )

    return entries


# Canonical OHLCV column names, keyed by their lower-case form. Used to
# normalize legacy CSVs that stored lower-case column headers.
_CANONICAL_COLUMNS = {
    "date": "Date",
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "adj close": "Adj Close",
    "volume": "Volume",
}


def _parse_date_column(series: pd.Series) -> pd.Series:
    """Parse a CSV 'Date' column that may hold ISO strings *or* legacy numeric
    day-numbers (matplotlib/epoch ordinals like 18292.0 written by older
    versions of this project). Returns a datetime series with unparseable
    values as NaT.
    """
    # Legacy format stored dates as plain numbers (days since the Unix epoch),
    # which pandas would otherwise mis-read as a calendar year (e.g. 18292).
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().all():
        return pd.to_datetime(numeric, unit="D", origin="unix", errors="coerce")

    return pd.to_datetime(series, errors="coerce")


def load_existing_history(path: Path) -> pd.DataFrame:
    """Load a ticker's local CSV history, or an empty DataFrame if absent.

    Handles both the current schema (Date, Open, High, Low, Close, Adj Close,
    Volume with ISO dates) and legacy CSVs that used lower-case headers, a
    leading unnamed index column, and numeric day-number dates.
    """
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()

    try:
        existing = pd.read_csv(path)
    except Exception as exc:
        print(f"Could not read existing CSV {path.name}: {exc}")
        return pd.DataFrame()

    if existing.empty:
        return pd.DataFrame()

    # Normalize headers to canonical names (legacy files used lower-case).
    existing = existing.rename(
        columns={col: _CANONICAL_COLUMNS.get(str(col).strip().lower(), col) for col in existing.columns}
    )

    # Drop stray columns from older saves (e.g. a leading unnamed index column
    # that could resurface as "Unnamed: 0").
    keep = [c for c in ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"] if c in existing.columns]
    existing = existing[keep]

    if "Date" not in existing.columns:
        print(f"Could not read existing CSV {path.name}: no 'Date' column; ignoring stored history")
        return pd.DataFrame()

    existing["Date"] = _parse_date_column(existing["Date"])
    existing = existing.dropna(subset=["Date"])
    if existing.empty:
        print(f"Could not parse any dates in {path.name}; ignoring stored history")
        return pd.DataFrame()

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


def plot_ticker(
    data: pd.DataFrame,
    ticker: str,
    output_path: Path,
    watchlist_limit: Optional[Tuple[Optional[float], Optional[float]]] = None,
) -> None:
    """Render a candlestick chart with 20/100-day MAs, limit lines, volume,
    and a trend indicator in the title, and save it to `output_path`.

    `watchlist_limit`, if given, is an optional (buy_limit, sell_limit) pair
    from an imported watchlist, drawn as dashed blue/purple lines in addition
    to the regular green/red 100-day-MA-range limit lines.
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

    if watchlist_limit is not None:
        buy_limit, sell_limit = watchlist_limit
        if buy_limit is not None:
            ax1.axhline(y=buy_limit, color="blue", linestyle="--", linewidth=1.2, label="Kauf Limit")
        if sell_limit is not None:
            ax1.axhline(y=sell_limit, color="purple", linestyle="--", linewidth=1.2, label="Verk. Limit")

    ax1.set_title(f"{ticker} Trend: {trend}")
    ax1.set_ylabel("Price")
    ax1.legend(loc="upper left")

    if "Volume" in view.columns:
        ax2.fill_between(dates_num, view["Volume"].values, 0, color="gray", alpha=0.4)
    dx = view["Adj Close"] - ma100.rolling(window=50).mean()
    ax2.plot(dates_num, dx.values, color="black", linewidth=1)
    ax2.set_ylabel("Volume / Delta")
    ax2.set_xlabel("Date")

    locator = mdates.AutoDateLocator()
    ax2.xaxis.set_major_locator(locator)
    ax2.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def process_ticker(
    ticker: str,
    run_folder: Path,
    today: date,
    watchlist_limit: Optional[Tuple[Optional[float], Optional[float]]] = None,
) -> None:
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
    plot_ticker(combined, ticker, image_path, watchlist_limit=watchlist_limit)
    print(f"{ticker}: chart saved -> {image_path.name}")


def _ask_stock_list_gui() -> Tuple[Optional[str], Optional[str]]:
    """Show a tkinter dialog to select the stock list source.

    Returns (stock_list_choice, xlsx_path) where stock_list_choice is one of
    'DEFAULT_LIST', 'SUPERVISION_LIST', or 'Aktienfinder', and xlsx_path is
    an optional file path (only relevant for Aktienfinder). Both are None if
    the user closes the window without pressing Start (cancelled).
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print("tkinter not available - falling back to DEFAULT_LIST")
        return "DEFAULT_LIST", None

    result: dict = {"choice": None, "xlsx": None}

    root = tk.Tk()
    root.title("Stock Downloader")
    root.resizable(False, False)

    tk.Label(
        root, text="Select ticker source:", font=("TkDefaultFont", 11, "bold"), pady=6
    ).pack(anchor="w", padx=16)

    choice_var = tk.StringVar(value="DEFAULT_LIST")

    options = [
        (f"Default List  ({', '.join(DEFAULT_LIST)})", "DEFAULT_LIST"),
        (f"Supervision List  ({len(SUPERVISION_LIST)} tickers)", "SUPERVISION_LIST"),
        ("Aktienfinder  (.xlsx export)", "Aktienfinder"),
    ]
    for label, value in options:
        tk.Radiobutton(root, text=label, variable=choice_var, value=value, anchor="w").pack(
            fill="x", padx=24
        )

    # --- Aktienfinder file picker (enabled only when that option is active) ---
    xlsx_frame = tk.Frame(root)
    xlsx_frame.pack(fill="x", padx=16, pady=(4, 2))
    tk.Label(xlsx_frame, text="xlsx file (leave blank to auto-detect):").pack(anchor="w")

    file_frame = tk.Frame(xlsx_frame)
    file_frame.pack(fill="x")
    xlsx_var = tk.StringVar()
    xlsx_entry = tk.Entry(file_frame, textvariable=xlsx_var, width=44, state="disabled")
    xlsx_entry.pack(side="left")

    def _browse() -> None:
        path = filedialog.askopenfilename(
            title="Select Aktienfinder export",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
        )
        if path:
            xlsx_var.set(path)

    browse_btn = tk.Button(file_frame, text="Browse...", command=_browse, state="disabled")
    browse_btn.pack(side="left", padx=4)

    def _on_choice_change(*_args: object) -> None:
        state = "normal" if choice_var.get() == "Aktienfinder" else "disabled"
        xlsx_entry.config(state=state)
        browse_btn.config(state=state)

    choice_var.trace_add("write", _on_choice_change)

    # --- Action buttons ---
    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=12)

    def _on_start() -> None:
        result["choice"] = choice_var.get()
        result["xlsx"] = xlsx_var.get().strip() or None
        root.destroy()

    def _on_cancel() -> None:
        root.destroy()

    tk.Button(btn_frame, text="Start", width=12, command=_on_start).pack(side="left", padx=8)
    tk.Button(btn_frame, text="Cancel", width=12, command=_on_cancel).pack(side="left", padx=8)

    root.mainloop()
    return result["choice"], result["xlsx"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments: positional tickers, or --xlsx to import a watchlist."""
    parser = argparse.ArgumentParser(description="Incremental Yahoo Finance downloader")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols to process")
    parser.add_argument(
        "--stock-list",
        type=_normalize_stock_list_choice,
        default="DEFAULT_LIST",
        help=(
            "Select ticker source when no positional tickers are passed: "
            "DEFAULT_LIST, SUPERVISION_LIST, or Aktienfinder (default: DEFAULT_LIST)"
        ),
    )
    parser.add_argument(
        "--xlsx",
        help=(
            "Path to an Aktienfinder.net-style watchlist .xlsx file to import tickers from "
            "(used when --stock-list Aktienfinder is selected; also works standalone for backward compatibility)"
        ),
    )
    parser.add_argument(
        "--sheet",
        default=0,
        help="Sheet name or 0-based index in the --xlsx file (default: first sheet)",
    )
    return parser.parse_args(argv)


def main() -> int:
    """Entry point: process CLI-provided tickers, an --xlsx watchlist, or
    DEFAULT_TICKERS if neither is given.
    """
    today = date.today()
    run_folder = ensure_directories(today)

    args = parse_args(sys.argv[1:])

    # When no CLI arguments are given, ask the user through a small GUI.
    gui_stock_list: Optional[str] = None
    gui_xlsx: Optional[str] = None
    if not args.tickers and not args.xlsx and args.stock_list == "DEFAULT_LIST":
        gui_stock_list, gui_xlsx = _ask_stock_list_gui()
        if gui_stock_list is None:
            print("Cancelled.")
            return 0

    watchlist_limits: dict[str, Tuple[Optional[float], Optional[float]]] = {}
    # Resolve effective values: GUI overrides the argparse defaults when the GUI ran.
    effective_stock_list = gui_stock_list if gui_stock_list is not None else args.stock_list
    effective_xlsx = gui_xlsx if gui_stock_list is not None else args.xlsx

    if args.tickers:
        tickers = args.tickers
    elif effective_stock_list == "Aktienfinder" or effective_xlsx:
        sheet = args.sheet
        if isinstance(sheet, str) and sheet.isdigit():
            sheet = int(sheet)

        xlsx_path = effective_xlsx
        if xlsx_path is None:
            from aktienfinder_stocklist import find_latest_export

            export_path = find_latest_export()
            xlsx_path = str(export_path)
            print(f"Aktienfinder list selected, using latest export: {xlsx_path}")

        entries = load_watchlist_from_xlsx(xlsx_path, sheet)
        tickers = [entry["ticker"] for entry in entries]
        for entry in entries:
            expected_currency = _expected_currency(entry["ticker"])
            buy = entry["buy_limit"] if entry["buy_currency"] in (None, expected_currency) else None
            sell = entry["sell_limit"] if entry["sell_currency"] in (None, expected_currency) else None
            if buy is not None or sell is not None:
                watchlist_limits[entry["ticker"]] = (buy, sell)
    elif effective_stock_list == "SUPERVISION_LIST":
        tickers = SUPERVISION_LIST
    else:
        tickers = DEFAULT_LIST

    print(f"Processing {len(tickers)} tickers: {', '.join(tickers)}")
    for ticker in tickers:
        try:
            process_ticker(ticker, run_folder, today, watchlist_limits.get(ticker))
        except Exception as exc:  # noqa: BLE001 - keep processing the rest of the list
            print(f"{ticker}: skipped due to unexpected error: {exc}")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
