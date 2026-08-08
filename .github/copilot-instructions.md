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
