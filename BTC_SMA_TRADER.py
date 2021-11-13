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
import logging
import os

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

# Crucial to set the BASE URL if doing paper trading IG. Not mentioned anywhere in docs.
os.environ['APCA_API_BASE_URL'] = 'https://paper-api.alpaca.markets'

pd.options.plotting.backend = "plotly"

# Tickers/Symbols to watch
ticker = "BTCUSD"

# The averages we want to collect. Since we are collecting hourly data but are using 5 and 13 day averages
# We need to multiply by 24 hours to ensure that the proper amount of data is used to calculate the averages.
# This offers higher resolution than just day to day transactions.
SMA_fast_period = 120 * 60
SMA_slow_period = 312 * 60

timeframe = TimeFrame.Minute

alpaca = api.REST()

logging.basicConfig(filename='trading.log', encoding='utf8', level=logging.INFO)

# Using a file to save last order because SMA's could be crossing again in data intake after inital order
with open('LastOperation.txt', 'r') as reader:

    # Worried about newline character affecting string evaluationss
    last_operation = reader.readline().replace('\n', '')

exec_time = 60
while True:

    # Data is collected every minute. Execution time is accounted for so that it always happens every minute
    # Unlikely that it needs to collect data every minute but with how volatile crypto markets are it cannot
    # hurt to be safe.

    time.sleep(60 - exec_time)
    start = time.time()
    
    # Dirty hack to get data we are collecting to be from past 14 days - present.
    end_date = datetime.datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days = 14)).strftime("%Y-%m-%d")

    # Gets all data and converts it to a pandas dataframe
    ticker_data = alpaca.get_crypto_bars(ticker, timeframe, start_date, end_date).df
    # Removes exchanges that arent CBSE
    ticker_data = ticker_data[ticker_data['exchange'] == 'CBSE']

    # This is what calculates the rolling averages
    ticker_data['fast_SMA'] = ticker_data['close'].rolling(SMA_fast_period).mean()
    ticker_data['slow_SMA'] = ticker_data['close'].rolling(SMA_slow_period).mean()

    full_ticker_data = ticker_data

    # Reassigns ticker_data to only keep three columns
    ticker_data = ticker_data[['close', 'fast_SMA', 'slow_SMA']]

    # Renames the close column to BTC
    ticker_data.rename(columns={'close': 'BTC'}, inplace=True)

    # This is the logic responsible for determining when it should be bought and sold.
    crossover = ticker_data[(ticker_data['fast_SMA'] > ticker_data['slow_SMA']) & (ticker_data['fast_SMA'].shift() < ticker_data['slow_SMA'].shift())]
    crossunder = ticker_data[(ticker_data['fast_SMA'] < ticker_data['slow_SMA']) & (ticker_data['fast_SMA'].shift() > ticker_data['slow_SMA'].shift())]
    
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
    # px.line(ticker_data[['BTC', 'fast_SMA', 'slow_SMA']], color_discrete_sequence=['red', 'green', 'blue']).show()

    # Renames the column that contains the buy/sell orders. When those columns are merged, no new column name is made.
    merged_orders.rename(columns={0 : 'ORDER'}, inplace=True)

    if(len(merged_orders.ORDER) != 0):
        operation = merged_orders['ORDER'].iloc[[-1]].to_frame().ORDER.item()
        print('\n' + 'Selected op: ' + operation)
        if(operation != last_operation):
            with open('LastOperation.txt', 'w') as file:
                if(operation == 'buy'):

                    # Will likely have to make it a limit order because I am trying to use exact amounts to purchase.
                    quantity = alpaca.get_account().buying_power / full_ticker_data['close'].iloc[[-1]].to_frame().close.item()
                    alpaca.submit_order(symbol=ticker, qty=quantity, type='market', side='buy', time_in_force='day')
                    logging.info('{0} Buying BTC'.format(time.strftime('%Y-%m-%d %I:%M:%S %p', time.localtime())))
                    file.write('buy')

                if(operation == 'sell'):

                    # Really only planning on trading BTC so I can liquidate all positions when I need to sell
                    alpaca.close_all_positions()
                    logging.info('{0} Selling BTC'.format(time.strftime('%Y-%m-%d %I:%M:%S %p', time.localtime())))
                    file.write('sell')
    else:
        print('No order made, will re-query in a minute!')
        logging.info('{0} No order made'.format(time.strftime('%Y-%m-%d %I:%M:%S %p', time.localtime())))

    # Calcs how much time it took to execute the above
    exec_time = time.time() - start

    # Due to this being a trading bot, we do not want to miss minute updates.
    if(exec_time > 60):
        logging.warning('{0} EXECUTION TIME EXCEEDED 60 SECONDS! RESETTING EXEC TIME!'.format(time.strftime('%Y-%m-%d %I:%M:%S %p', time.localtime())))
        exec_time = 60

    print('It took {0} second(s) to get data and find entry / exit points!'.format(round(exec_time, 1)))