# -*- coding: utf-8 -*-
"""
Created on Thu Jan 14 11:39:22 2021

@author: vollmera

Legacy exploratory script: downloads a single ticker (AAPL) and renders a
basic candlestick + 100-day moving-average chart. Superseded by main.py,
which adds incremental downloads, CSV persistence, and limit indicators.
Kept here for reference only.
"""



import yfinance as yf

import matplotlib.pyplot as plt
import seaborn
import pandas as pd

import matplotlib.dates as mdates
from matplotlib.patches import Rectangle

from datetime import date

try:
    from mplfinance.original_flavor import candlestick_ohlc
except ImportError:
    def candlestick_ohlc(ax, quotes, width=0.2, colorup="g", colordown="r", alpha=0.8):
        for quote in quotes:
            date_num, open_price, high, low, close = quote[:5]
            color = colorup if close >= open_price else colordown
            rect = Rectangle(
                (date_num - width / 2, min(open_price, close)),
                width,
                abs(close - open_price),
                facecolor=color,
                edgecolor=color,
                alpha=alpha,
            )
            ax.add_patch(rect)
            ax.vlines(date_num, low, high, color=color, alpha=alpha, linewidth=1)

today = date.today()
print("Today's date:", today)

try:
    msft = yf.Ticker("MSFT")
    hist = msft.history(period="5d")
except Exception as exc:
    print("Failed to load ticker history:", exc)
    hist = None

try:
    df = yf.download("AAPL", start="2020-02-01", end=today)
    if df is None or df.empty:
        print("No data returned for AAPL")
        raise ValueError("No data returned")
except Exception as exc:
    print("Failed to download AAPL data:", exc)
    df = pd.DataFrame()

if not df.empty:
    df_ohlc = df["Adj Close"].resample("10D").ohlc()
    df_Volume = df["Volume"].resample("10D").sum()
    df_100ma = df["Adj Close"].rolling(window=100).mean()
    df_dx = (df["Adj Close"] - df_100ma.rolling(window=50).mean())
    df_ohlc.reset_index(inplace=True)
    df_ohlc["Date"] = df_ohlc["Date"].map(mdates.date2num)

    ax1 = plt.subplot2grid((6, 1), (0, 0), rowspan=5, colspan=1)
    ax2 = plt.subplot2grid((6, 1), (5, 0), rowspan=5, colspan=1, sharex=ax1)
    ax1.xaxis_date()
    candlestick_ohlc(ax1, df_ohlc.values, width=2, colorup="g")
    ax1.plot(df_100ma.index.map(mdates.date2num), df_100ma.values)
    ax2.plot(df_dx.index.map(mdates.date2num), df_dx.values)
    plt.show()
else:
    print("Skipping plot because no market data was available.")






