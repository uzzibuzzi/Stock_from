import yfinance as yf
import os

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

# creates rolling means acoring the list sind back string for positive or neagtive trend
def fastAnalyse(series):
    avrg=[2,5,15,25,50,200]
    resultStr=""
    for i in avrg:
        mean_gradient=series.rolling(window=i).mean().diff()[-1]
        #print(mean_gradient)
        if mean_gradient > 0 :
            resultStr=resultStr + "+"
        else :
            resultStr=resultStr+"-"
    return resultStr


def get_Data_yahoo(ticker):
    tickerSymbol = ticker
    stockName = ticker

    try:
        msft = yf.Ticker(tickerSymbol)
        stockinfo = msft.info
        if stockinfo and stockinfo.get("longName"):
            stockName = str(stockinfo.get("longName"))
    except Exception as exc:
        print("failed Ticker", tickerSymbol, exc)

    try:
        df = yf.download(tickerSymbol, start="2020-02-01", end=today)
        if df is None or df.empty:
            print("No data returned for", tickerSymbol)
            return stockName, pd.DataFrame()
    except Exception as exc:
        failList.append(tickerSymbol)
        print("failed download", tickerSymbol, exc)
        return stockName, pd.DataFrame()

    return stockName, df





today = date.today()
print("Today's date:", today)



mySupervisionList=["2338.HK","AAG.DE","BIDU","BMW.DE","BAYN.DE","COK.DE","CSCO","EVD.DE","FEV.DE","HAG.F","IRBT","JD","MTX.DE","N7G.DE","PRLB","SHL.DE","SIX2.DE","SLM","TCOM","TUI1.DE","VOW3.DE"]
failList=[]
RSL_List=[]
trendIndicatorList=[]
mdf=pd.DataFrame()
stockNameList=[]

tickerSymbol="2338.HK"



wahtchList=["2338.HK","SW1.F","SLT.DE","ASL.de"]
#mySupervisionList=wahtchList

try:
    os.mkdir("pics//"+str(today))
except OSError:
    print ("Creation of the directory failed" )
else:
    print ("Successfully created the directory " )
    
for i in range(len(mySupervisionList)):   
    stockName,df = get_Data_yahoo(mySupervisionList[i])   
    print(stockName)
    if (len(df) <1):
        pass
    else:
        df_ohlc=df["Adj Close"].resample("1D").ohlc()
        df_ohlc_2d=df["Adj Close"].resample("2D").ohlc()
        
        df_Volume = df["Volume"].resample("2D").sum()
        df_100ma=df["Adj Close"].rolling(window=100).mean()
        df_20ma=df["Adj Close"].rolling(window=20).mean()
        df_dx= (df["Adj Close"]-df_100ma.rolling(window=50).mean())
        df_ohlc.reset_index(inplace=True)
        df_ohlc["Date"]=  df_ohlc_2d["Date"].map(mdates.date2num)
        RSL=df["Adj Close"].rolling(window=3).mean()/df["Adj Close"].rolling(window=5*26).mean()
        RSL_List.append(RSL[-1])
        trendIndicator=fastAnalyse(df["Adj Close"])
        trendIndicatorList.append(trendIndicator)
        stockNameList.append(str(stockName))
        df_ohlc.to_csv("save\\"+str(stockName)+".csv")

        ax1=plt.subplot2grid((6,1),(0,0),rowspan=5,colspan=1)
        plt.title(str(stockName)+" RSL : "+str(RSL[-1])[:4]+trendIndicator)
        ax2=plt.subplot2grid((6,1),(5,0),rowspan=5,colspan=1,sharex=ax1)
        ax1.xaxis_date()
        candlestick_ohlc(ax1,df_ohlc.values,width=2,colorup="g")
        ax1.plot(df_100ma.index.map(mdates.date2num),df_100ma.values)
        ax1.plot(df_20ma.index.map(mdates.date2num),df_20ma.values)
        ax1.axhline(y=df_100ma.max(), color='g', linestyle='-')
        ax1.axhline(y=df_100ma.min(), color='r', linestyle='-')
        ax2.fill_between(df_Volume.index.map(mdates.date2num), df_Volume.values,0)
        ax2.plot(df_dx.index.map(mdates.date2num),df_dx.values) 
        plt.savefig("pics\\"+str(today)+"\\"+str(stockName).split(".")[0]+str(today), dpi=800)
        plt.show()
    
   


mdf=pd.DataFrame({"mySupervisionList":stockNameList,"RSL_List":RSL_List,"trendIndicator":trendIndicatorList}) 
mdf.to_csv("Result_"+str(today)+".csv")



