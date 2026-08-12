# Stock_from

Downloads daily OHLCV history for a list of tickers from Yahoo Finance,
persists it incrementally as local CSV files, and renders a candlestick chart
with trend/limit indicators for each ticker.

## Requirements

- Python 3.9+
- Packages: `pandas`, `yfinance`, `matplotlib`

Install dependencies:

```powershell
pip install pandas yfinance matplotlib
```

## Running the workflow

The entry point is [`main.py`](main.py). Run it with no arguments to process
the built-in default ticker list, or pass one or more ticker symbols to
process only those:

```powershell
# Process the default ticker list
python main.py

# Process the full supervision ticker list
python main.py --stock-list SUPERVISION_LIST

# Process an Aktienfinder list from the latest export in Downloads
python main.py --stock-list Aktienfinder

# Process an Aktienfinder list from a specific export file
python main.py --stock-list Aktienfinder --xlsx "C:/path/to/export.xlsx"

# Process specific tickers
python main.py AAPL MSFT
```

Each run will:

1. Load any existing history for a ticker from `save/<ticker>.csv`, if present.
2. Download only the rows missing since the last stored date (or from
   `2020-01-01` if no local history exists yet).
3. Merge the new rows into the existing data, remove duplicate dates, and
   overwrite `save/<ticker>.csv`.
4. Render a chart with 20-day/100-day moving averages, green/red limit lines
   based on the recent 100-day moving-average range, and a trend indicator in
   the title, saving it to `pics/<today>/<ticker>_<today>.png`.

Running the script again on a later day only downloads and appends the new
rows — it does not re-download or duplicate existing history.

## Project layout

- [`main.py`](main.py) — current, supported entry point described above.
- [`save/`](save/) — local per-ticker CSV history (created automatically).
- [`pics/`](pics/) — generated charts, one dated subfolder per run.
- [`yahoo_finance_api.py`](yahoo_finance_api.py), [`yahoo_plot.py`](yahoo_plot.py),
  [`getData.py`](getData.py) — earlier, exploratory scripts kept for reference;
  superseded by `main.py`.
- [`calc_knock_out_perfomance.py`](calc_knock_out_perfomance.py) — standalone
  knock-out option payoff calculator, unrelated to the download/chart workflow.
- [`tests/`](tests/) — smoke tests covering CSV persistence and chart output.

## Tests

Smoke tests mock the Yahoo Finance download so they run without network
access:

```powershell
python -m unittest discover -s tests -v
```
