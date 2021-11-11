# Alpaca for data
from numpy import isfinite
import alpaca_trade_api as api
from alpaca_trade_api.rest import TimeFrame

# pandas for analysis
import pandas as pd
import numpy as np
# Plotly for charting
import plotly.graph_objects as go
import plotly.express as px

import datetime
from datetime import date
import time


"""
TODO: 
    Currently I am receiving hourly data but it doesn't seem to be the most current data.
    It might be sending back the server time which is why I might be confused. Make sure 
    that it is sending the most current information

    Figure out a super redundant way to judge when to make buy or sell calls. Try to make it 
    so no data needs to be stored on the device to make buying decisions. I think upon first bootup, 
    it should query the API to see if it has equity or not. If it doesn't, then it should continously, 
    expand timeframe to see if its in a bull phase or a bear phase.

    On startup it should determine when it should make the hourly calls. Preferably right when the 
    new hour starts.
"""   

# Set default charting for pandas to plotly
pd.options.plotting.backend = "plotly"

# Tickers/Symbols to watch
btc = "BTCUSD"

# The averages we want to collect. Since we are collecting hourly data but are using 5 and 13 day averages
# We need to multiply by 24 hours to ensure that the proper amount of data is used to calculate the averages.
# This offers higher resolution than just day to day transactions.
SMA_fast_period = 120
SMA_slow_period = 312

timeframe = TimeFrame.Hour

alpaca = api.REST(API_KEY, API_SECRET_KEY)

last_operation = 'sell'

# Start and End date of the data for backtest
exec_time = 60
while True:
    # Will have it collect data every hour not 60 min. Doesn't make sense especially when timeframe is set
    # to hour
    time.sleep(60 - exec_time)
    start = time.time()

    # Dirty hack to get data we are collecting to be from past 14 days - present.
    end_date = datetime.datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days = 100)).strftime("%Y-%m-%d")

    # Gets all data and converts it to a pandas dataframe
    btc_data = alpaca.get_crypto_bars(btc, timeframe, start_date, end_date).df
    # Removes exchanges that arent CBSE
    btc_data = btc_data[btc_data['exchange'] == 'CBSE']

    # This is what calculates the rolling averages
    btc_data['fast_SMA'] = btc_data['close'].rolling(SMA_fast_period).mean()
    btc_data['slow_SMA'] = btc_data['close'].rolling(SMA_slow_period).mean()

    # Reassings btc_data to only keep three columns
    btc_data = btc_data[['close', 'fast_SMA', 'slow_SMA']]

    # Renames the close column to BTC
    btc_data.rename(columns={'close': 'BTC'}, inplace=True)

    # This is the logic responsible for determining when it should be bought and sold.
    crossover = btc_data[(btc_data['fast_SMA'] > btc_data['slow_SMA']) & (btc_data['fast_SMA'].shift() < btc_data['slow_SMA'].shift())]
    crossunder = btc_data[(btc_data['fast_SMA'] < btc_data['slow_SMA']) & (btc_data['fast_SMA'].shift() > btc_data['slow_SMA'].shift())]
    
    # These next few lines just reformat the Dataframe to replace prices with buy/sell and restructure columns.
    crossover[['BTC', 'fast_SMA', 'slow_SMA']] = 'buy'
    crossover = crossover[['BTC']]
    crossover.rename(columns={'BTC' : 'BUY_SIG'}, inplace=True)

    crossunder[['BTC', 'fast_SMA', 'slow_SMA']] = 'sell'
    crossunder = crossunder[['BTC']]
    crossunder.rename(columns={'BTC' : 'SELL_SIG'}, inplace=True)

    # Prints out a merged dataframe showing when the buy and sell calls happen
    merged_orders = pd.merge(crossover, crossunder, how="outer", left_index=True, right_index=True).fillna('').sum(1).replace('', np.nan).to_frame()

    # Charts BTC, Fast_sma, and slow_sma
    # px.line(btc_data[['BTC', 'fast_SMA', 'slow_SMA']], color_discrete_sequence=['red', 'green', 'blue']).show()

    # Renames the column that contains the buy/sell orders. When those columns are merged, no new column name is made.
    merged_orders.rename(columns={0 : 'ORDER'}, inplace=True)
    if(len(merged_orders.ORDER) != 0):
        operation = merged_orders['ORDER'].iloc[[-1]].to_frame().ORDER.item()
        if(operation != last_operation):
            print(alpaca.get_account())
    # Calcs how much time it took to execute the above
    exec_time = time.time() - start

    # Due to this being a trading bot, we do not want to miss minute updates.
    if(exec_time > 60):
        print('EXECUTION TIME EXCEEDED 60 SECONDS! RESETTING EXEC TIME!')
        exec_time = 0
    print('It took {0} second(s) to get data and find entry / exit points!'.format(round(exec_time, 1)))