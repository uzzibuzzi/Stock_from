import os
import time
import pandas_datareader as web
from winotify import Notification, audio
print("don2")
tickers=["AAPL","FB"]
for ticker in tickers:
    print(web.DataReader(ticker,"yahoo").iloc[-1]["Close"])
