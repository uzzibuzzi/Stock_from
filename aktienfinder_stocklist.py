"""Build a stock list from an Aktienfinder.Net Excel export.

Aktienfinder.Net ("Qualitaetsaktien finden") lets you export the current
screener result to an .xlsx file. The newest export usually lands in your
Downloads folder as::

    Aktienfinder.Net - Qualitaetsaktien finden (N).xlsx

where ``(N)`` is an incrementing counter the browser appends to avoid
overwriting older downloads.

This module locates the newest such export, parses it into a tidy
``pandas.DataFrame`` and derives a yfinance-ready ``ticker`` column from the
sheet's ``Symbol`` and ``Land`` (country) columns. Actually fetching data from
yfinance is intentionally out of scope -- this only produces the list.

Usage:
    python aktienfinder_stocklist.py
    python aktienfinder_stocklist.py --file "C:/path/to/export.xlsx"
    python aktienfinder_stocklist.py --csv stocklist.csv
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

# Glob used to discover exports in the Downloads folder. The trailing wildcard
# covers both the base name and the "(N)" suffixed variants.
EXPORT_GLOB = "Aktienfinder.Net*.xlsx"

# Excel writes a hidden lock/owner file prefixed with "~$" while a workbook is
# open. Those must never be treated as a real export.
_LOCK_PREFIX = "~$"

# Matches the "(N)" counter the browser appends, e.g. "... finden (8).xlsx".
_SUFFIX_RE = re.compile(r"\((\d+)\)")

# Columns we keep, mapped from the German export header to tidy snake_case
# names. Everything else in the (very wide) sheet is dropped.
_COLUMN_MAP = {
    "ISIN": "isin",
    "Symbol": "symbol",
    "Aktie": "name",
    "Kurs": "kurs",
    "Kauf Limit": "kauf_limit",
    "Verk. Limit": "verk_limit",
    "Land": "land",
}

# Maps the export's German country names to the yfinance exchange suffix.
# Unmapped/unknown countries deliberately get no suffix (bare symbol) so we can
# evaluate how well yfinance resolves them; see build_ticker().
COUNTRY_SUFFIX = {
    "Deutschland": ".DE",
    "USA": "",
    "Vereinigte Staaten": "",
    "Schweiz": ".SW",
    "Frankreich": ".PA",
    "Niederlande": ".AS",
    "Grossbritannien": ".L",
    "Großbritannien": ".L",
    "Vereinigtes Koenigreich": ".L",
    "Vereinigtes Königreich": ".L",
    "Italien": ".MI",
    "Spanien": ".MC",
    "Kanada": ".TO",
    "Belgien": ".BR",
    "Oesterreich": ".VI",
    "Österreich": ".VI",
    "Schweden": ".ST",
    "Daenemark": ".CO",
    "Dänemark": ".CO",
    "Finnland": ".HE",
    "Norwegen": ".OL",
    "Portugal": ".LS",
    "Irland": ".IR",
    "Japan": ".T",
    "Australien": ".AX",
    "Hongkong": ".HK",
}


def _suffix_number(path: Path) -> int:
    """Return the "(N)" counter in a file name, or 0 when there is none.

    The base export ("... finden.xlsx") has no counter and is treated as the
    oldest (0). Numbers are compared as integers so "(10)" ranks above "(9)".
    """
    match = _SUFFIX_RE.search(path.stem)
    return int(match.group(1)) if match else 0


def default_downloads_dir() -> Path:
    """Return the current user's Downloads folder."""
    return Path.home() / "Downloads"


def find_latest_export(downloads_dir: Path | str | None = None) -> Path:
    """Return the newest Aktienfinder export in ``downloads_dir``.

    "Newest" is the file with the highest "(N)" counter in its name. Excel lock
    files ("~$...") are ignored.

    Raises:
        FileNotFoundError: if no matching export exists.
    """
    directory = Path(downloads_dir) if downloads_dir is not None else default_downloads_dir()
    candidates = [
        path
        for path in directory.glob(EXPORT_GLOB)
        if path.is_file() and not path.name.startswith(_LOCK_PREFIX)
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No files matching '{EXPORT_GLOB}' found in {directory}."
        )
    return max(candidates, key=_suffix_number)


def build_ticker(symbol: str, land: str) -> str:
    """Build a yfinance ticker from an export ``symbol`` and ``land``.

    The symbol is used as-is (no class-share normalization). The exchange
    suffix is looked up from ``COUNTRY_SUFFIX``; unknown countries yield the
    bare symbol.
    """
    base = str(symbol).strip()
    country = str(land).strip()
    suffix = COUNTRY_SUFFIX.get(country, "")
    return f"{base}{suffix}"


def load_stock_list(path: Path | str | None = None) -> pd.DataFrame:
    """Load an Aktienfinder export into a tidy DataFrame.

    Args:
        path: The .xlsx file to read. Defaults to the newest export found via
            find_latest_export().

    Returns:
        A DataFrame with columns isin, symbol, name, kurs, kauf_limit,
        verk_limit, land and a derived yfinance-ready ``ticker`` column.
    """
    export_path = Path(path) if path is not None else find_latest_export()

    raw = pd.read_excel(export_path, engine="openpyxl")

    available = {col: tidy for col, tidy in _COLUMN_MAP.items() if col in raw.columns}
    df = raw[list(available)].rename(columns=available).copy()

    df["ticker"] = [
        build_ticker(sym, land)
        for sym, land in zip(df.get("symbol", ""), df.get("land", ""))
    ]

    ordered = ["ticker", "symbol", "isin", "name", "kurs", "kauf_limit", "verk_limit", "land"]
    return df[[col for col in ordered if col in df.columns]]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a yfinance-ready stock list from an Aktienfinder.Net export."
    )
    parser.add_argument(
        "--downloads-dir",
        type=Path,
        default=None,
        help="Folder to search for the export (default: the user's Downloads).",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Use this specific .xlsx export instead of auto-detecting.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Also write the resulting stock list to this CSV path.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    export_path = args.file
    if export_path is None:
        export_path = find_latest_export(args.downloads_dir)

    print(f"Reading: {export_path}")
    df = load_stock_list(export_path)

    print(f"Parsed {len(df)} stocks.\n")
    with pd.option_context("display.max_rows", None, "display.width", None):
        print(df.to_string(index=False))

    if args.csv is not None:
        df.to_csv(args.csv, index=False)
        print(f"\nWrote CSV: {args.csv}")


if __name__ == "__main__":
    main()
