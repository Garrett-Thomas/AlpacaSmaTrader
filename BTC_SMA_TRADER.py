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
from datetime import date

import datetime
import time
import logging
import smtplib
import ssl
import os


def getLocFormatTime():
    return time.strftime('%Y-%m-%d %I:%M:%S %p', time.localtime())

# This function sends an email when the server encounters a fatal error or when orders are executed.
def sendMessage(subject, content):
    server = smtplib.SMTP(HOST, port=587)
    server.starttls(context=ssl.create_default_context())
    server.login(EMAIL, EMAIL_PASSWD)
    server.sendmail(EMAIL, [EMAIL_TO], "Subject:" + subject + "\n\n" + content)
    server.quit()


# Crucial to set the BASE URL if doing paper trading IG. Not mentioned anywhere in docs.
os.environ['APCA_API_BASE_URL'] = 'https://paper-api.alpaca.markets'

# Grabbing environment variables
EMAIL = os.getenv('TRADING_EMAIL')
EMAIL_PASSWD = os.getenv('EMAIL_PASSWD')
EMAIL_TO = os.getenv('EMAIL_RECEIVER')
HOST = os.getenv('SMTP_URL')

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

logging.basicConfig(filename='trading.log',
                    encoding='utf8', level=logging.INFO)

# Using a file to save last order because SMA's could be crossing again in data intake after inital order
with open('LastOperation.txt', 'r') as reader:

    # Worried about newline character affecting string evaluationss
    last_operation = reader.readline().replace('\n', '')

exec_time = 60
num_tries = 0


while True:

    try:
        # Data is collected every minute. Execution time is accounted for so that it always happens every minute
        # Unlikely that it needs to collect data every minute but with how volatile crypto markets are it cannot
        # hurt to be safe.
        time.sleep(60 - exec_time)
        start = time.time()

        # Dirty hack to get data we are collecting to be from past 14 days - present.
        end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.datetime.now() -
                      datetime.timedelta(days=14)).strftime("%Y-%m-%d")

        # Gets all data and converts it to a pandas dataframe
        ticker_data = alpaca.get_crypto_bars(
            ticker, timeframe, start_date, end_date).df
        # Removes exchanges that arent CBSE
        ticker_data = ticker_data[ticker_data['exchange'] == 'CBSE']

        # This is what calculates the rolling averages
        ticker_data['fast_SMA'] = ticker_data['close'].rolling(
            SMA_fast_period).mean()
        ticker_data['slow_SMA'] = ticker_data['close'].rolling(
            SMA_slow_period).mean()

        full_ticker_data = ticker_data

        # Reassigns ticker_data to only keep three columns
        ticker_data = ticker_data[['close', 'fast_SMA', 'slow_SMA']]

        # Renames the close column to BTC
        ticker_data.rename(columns={'close': 'BTC'}, inplace=True)

        # This is the logic responsible for determining when it should be bought and sold.
        crossover = ticker_data[(ticker_data['fast_SMA'] > ticker_data['slow_SMA']) & (
            ticker_data['fast_SMA'].shift() < ticker_data['slow_SMA'].shift())]
        crossunder = ticker_data[(ticker_data['fast_SMA'] < ticker_data['slow_SMA']) & (
            ticker_data['fast_SMA'].shift() > ticker_data['slow_SMA'].shift())]

        # These next few lines just reformat the Dataframe to replace prices with buy/sell and restructure columns.
        crossover[['BTC', 'fast_SMA', 'slow_SMA']] = 'buy'
        crossover = crossover[['BTC']]
        crossover.rename(columns={'BTC': 'BUY_SIG'}, inplace=True)

        crossunder[['BTC', 'fast_SMA', 'slow_SMA']] = 'sell'
        crossunder = crossunder[['BTC']]
        crossunder.rename(columns={'BTC': 'SELL_SIG'}, inplace=True)

        # Prints out a merged dataframe showing when the buy and sell calls happen
        merged_orders = pd.merge(crossover, crossunder, how="outer", left_index=True, right_index=True).fillna(
            '').sum(1).replace('', np.nan).to_frame()

        # Charts BTC, Fast_sma, and slow_sma
        px.line(ticker_data[['BTC', 'fast_SMA', 'slow_SMA']],
                color_discrete_sequence=['red', 'green', 'blue']).show()

        # Renames the column that contains the buy/sell orders. When those columns are merged, no new column name is made.
        merged_orders.rename(columns={0: 'ORDER'}, inplace=True)

        # Don't want to make an order if there is no SMA intersection
        if(len(merged_orders.ORDER) != 0):
            operation = merged_orders['ORDER'].iloc[[-1]
                                                    ].to_frame().ORDER.item()
            # A case might arise where the same operation is seen multiple times. Do not want to
            # make the same order twice.
            if(operation != last_operation):

                print('\t' + 'Selected operation: ' + operation)
                with open('LastOperation.txt', 'w') as file:
                    if(operation == 'buy'):

                        # Making this a limit order for exactness's sake.
                        # Query the api for data right before submitting the order so that 
                        # data is the most current
                        quantity = float(alpaca.get_account().equity) / \
                            (full_ticker_data['close'].iloc[[-1]].to_frame().close.item())
                        alpaca.submit_order(symbol=ticker, qty=quantity, type='limit', side='buy', limit_price=alpaca.get_crypto_bars(ticker, timeframe, datetime.datetime.now(
                        ).strftime("%Y-%m-%d"), datetime.datetime.now().strftime("%Y-%m-%d")).df['close'].iloc[[-1]].to_frame().close.item(), time_in_force='day')
                        logging.info('{0} Buying BTC'.format(getLocFormatTime()))
                        file.write('buy')
                        sendMessage('Order Status', 'Bought {0} of {1}'.format(round(quantity, ndigits=3), ticker))

                    elif(operation == 'sell'):

                        # Really only planning on trading BTC so I can liquidate all positions when I need to sell
                        alpaca.close_all_positions()
                        logging.info(
                            '{0} Selling BTC'.format(getLocFormatTime()))
                        file.write('sell')
                        sendMessage('Order Status', 'Liquidated all positions. Account equity is currently ${0}'.format(alpaca.get_account().equity))

        else:   
            print('No order made, will re-query in a minute!')
            logging.info('{0} No order made'.format(getLocFormatTime()))

        # Calcs how much time it took to execute the above
        exec_time = time.time() - start

        # Due to this being a trading bot, we do not want to miss minute updates.
        if(exec_time > 60):
            logging.warning('{0} EXECUTION TIME EXCEEDED 60 SECONDS! RESETTING EXEC TIME!'.format(
                time.strftime('%Y-%m-%d %I:%M:%S %p', time.localtime())))
            exec_time = 60

        print(
            'It took {0} second(s) to get data and find entry / exit points!'.format(round(exec_time, 1)))

    except Exception as e:

        logging.error('{0} ERROR! \n {1}'.format(getLocFormatTime(), e))
        if(num_tries < 3):

            # This will make the program sleep for 5 minutes in between errors.
            # It will try three times before quitting
            exec_time = -240
            num_tries += 1

        else:
            print(e)
            sendMessage('Server Status', 'Fatal error, program exiting')
            quit()
