# Smoothed Moving Average Bitcoin Trader
A trading bot using the 5 and 13 day SMA strategy.

It recalculates the averages every minute. Will send a message on trade executions and server errors.
# How to Run the Bot?
1. Clone repo and install pip requirements

    `pip install -r requirements.txt`

---
2. Set Environment Variables (Fill in your info between quotes)

    ```
    cat <<EOF>> ~/.zprofile
    export APCA_API_KEY_ID=""
    export APCA_API_SECRET_KEY=""
    export TRADING_EMAIL=""
    export EMAIL_PASSWD=""
    export EMAIL_RECEIVER=""
    export SMTP_URL=""
    EOF
    ```
---
3. Let 'er rip!

    `python3 BTC_SMA_TRADER.py`

---

## Note
The current script is set up for paper trading.
To live trade, remove the line
```
    os.environ['APCA_API_BASE_URL'] = 'https://paper-api.alpaca.markets'
```