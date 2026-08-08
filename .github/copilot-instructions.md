# Stock from troubleshooting notes

## Yahoo finance script reliability fixes

The script in yahoo_finance_api.py was failing because it relied on older plotting compatibility and assumed every Yahoo Finance download would succeed.

### What was fixed
- Replaced the deprecated mpl_finance import path with a compatibility fallback.
- Added a safe fallback renderer for candlestick charts so the script can run even when mplfinance is unavailable.
- Hardened the Yahoo download helper to handle empty or failed responses without crashing.
- Guarded ticker lookup failures so the script continues processing the rest of the list.

### Practical guidance
- Prefer using the current Matplotlib-compatible plotting path where possible.
- Always check whether a downloaded DataFrame is empty before resampling or plotting it.
- Treat ticker lookups and network downloads as fallible operations.

### Files involved
- yahoo_finance_api.py

## Main entry-point findings

The project needs one clear entry script (`main.py`) that updates local stock history incrementally and regenerates plots in the existing visual style.

### What should be implemented
- Read the ticker list and iterate all symbols.
- Reuse local CSV files from the `save` folder.
- If a CSV exists, detect the last stored date and download only missing rows until today.
- Merge, de-duplicate by date, sort, and write back to the same CSV.
- Save images to the `pics` folder.

### Plot requirements
- Keep candlestick-like price view.
- Keep trend-following overlays (20-day and 100-day moving averages).
- Keep existing limit logic (upper/lower guide lines based on moving-average range).
- Include trend indicator output in the chart title.

### Test checkpoints
- First run creates CSV and picture output for selected tickers.
- Second run only appends missing dates and does not duplicate existing rows.
- Output pictures include trend overlays and limit guides.
