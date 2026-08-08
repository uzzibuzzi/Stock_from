"""Legacy scratch script using pandas_datareader + winotify (Windows only).

Not part of the current workflow; kept for reference only. Prefer main.py,
which uses yfinance directly and persists incremental history to save/.
"""
import os
import time
import pandas_datareader as web
from winotify import Notification, audio
print("don2")
tickers=["AAPL","FB"]
for ticker in tickers:
    # Fetch the latest closing price for each ticker via pandas_datareader.
    print(web.DataReader(ticker,"yahoo").iloc[-1]["Close"])
