#used in orded tom calculate the RSI
import pandas as pd

#used to calculate the volatility
import numpy as np

from ibapi.common import TagValueList, TickerId
from ibapi.contract import Contract
from ibapi.client import *
from ibapi.wrapper import *
from ibapi.tag_value import TagValue
import datetime
import time
import threading

#port number for the TWS API (paper trading: 7497, live trading: 7496)
port = 7497

#initialize the bank and position_ref dictionaries
bank = {}
position_ref = {}

#NASDAQ stock exchange
nasdaq_100_list = [ 
    "AAPL", "ADBE", "ADI", "ADP", "ADSK", "ALGN", "ALXN", "AMAT", "AMD", "AMGN", "AMZN", "ANSS", "ASML", "ATVI", "AVGO", "BIDU", "BIIB", "BKNG", "BMRN", "CDNS", "CDW", "CERN", "CHKP", "CHTR", "CMCSA", "COST", "CPRT", "CSCO", "CSX", "CTAS", "CTSH", "CTXS", "DLTR", "DOCU", "DXCM", "EA", "EBAY", "EXC", "EXPE", "FAST", "FB", "FISV", "FOX", "FOXA", "GILD", "GOOG", "GOOGL", "IDXX", "ILMN", "INCY", "INTC", "INTU", "ISRG", "JD", "KDP", "KHC", "KLAC", "LRCX", "LULU", "MAR", "MCHP", "MDLZ", "MELI", "MNST", "MSFT", "MU", "MXIM", "NFLX", "NTAP", "NTES", "NVDA", "NXPI", "ORLY", "PAYX", "PCAR", "PDD", "PEP", "PYPL", "QCOM", "REGN", "ROST", "SBUX", "SIRI", "SNPS", "SPLK", "SWKS", "TCOM", "TMUS", "TSLA", "TXN", "VRSK", "VRSN", "VRTX", "WBA", "WDAY", "XEL", "XLNX", "ZM"
]


class reversionOfMeanApp(EWrapper, EClient):
    #basic setup function
    def __init__(self):
        EClient.__init__(self, self)
        #initialize the historical data list
        self.historicalData = []

    #function to get the next valid id, called by the TWS API
    def nextValidId(self, orderId: OrderId):
        self.orderId = orderId

    #insures each order has a unique id by incrementing the order id
    def nextId(self):
        self.orderId += 1
        return self.orderId
    
    #function to process error messages from the TWS API
    def error(self, reqId, errorCode, errorString, advancedOrderReject = None):
        print(f"reqId: {reqId}, errorCode: {errorCode}, errorString: {errorString}, orderReject: {advancedOrderReject}")

    #function used to update account information and account balance, pull from this function when trying to get account balance
    def updateAccountValue(self, key, val, currency, accountName):
        if key == "TotalCashBalance" and currency == "BASE":
          bank[key] = float(val)

          # If we drop below $1M, disconnect this is a fail safe
          if float(val) <1000000:
              self.disconnect()

    #updates the position of the stock in the position_ref dictionary
    def position(self, account, contract, position, avgCost):
        position_ref[contract.symbol] = position

    #scanner function to get the top 5 stocks, this can be altered to get different stocks 
    def scannerData(self, reqId, rank, contractDetails, distance, benchmark, projection, legsStr):
        #this will allow us to only trade the top 5 stocks for the day 
        if rank < 5:
            rankId = rank+reqId
            bank[rankId] = {"contract": contractDetails.contract}
            position_ref[contractDetails.contract.symbol] = 0
            app.reqMktData(rankId, contractDetails.contract, "", False, False, [])
            print(f"Rank {rank} Contract: {contractDetails.contract.symbol} @ {contractDetails.contract.exchange}")

            #calculate and print the volatility of the stock
            volatility = self.calculateVolatility(contractDetails.contract.symbol)
            print(f"Volatility for: {contractDetails.contract.symbol} is: {volatility}")

    #end the scanner
    def scannerDataEnd(self, reqId):
        self.cancelScannerSubscription(reqId)


    #implemenation of the trading strategy
    def tickPrice(self, reqId, tickType, price, attrib):

        #if the last tick type is in the bank array
        if "LAST" not in bank[reqId].keys():
            bank[reqId]["LAST"] = price

        bankTick = bank[reqId]["LAST"]
        bankContract = bank[reqId]["contract"]

        #create a new order class, tif is DAY (meaning order will be good for the day)
        order = Order()
        order.tif = "DAY"
        order.totalQuantity = 5
        order.orderType = "MKT"

        # If the new price is more than 5% higher than our previous price point.
        if (bankTick * 1.05) < price:
            order.action = "BUY"
            app.placeOrder(app.nextId(), bankContract, order)
        # If the new price is less than 6% of our previous price point
        elif (bankTick * 0.94) > price and position_ref[bankContract.symbol] >= 5:
            order.action = "SELL"
            app.placeOrder(app.nextId(), bankContract, order)

        bank[reqId]["LAST"] = price

    #checks if the order was rejected
    def openOrder(self, orderId, contract, order, orderState):
        if orderState.status == "Rejected":
            print(f"{datetime.datetime.now()} {orderState.status}: ID:{orderId} || {order.action} {order.totalQuantity} {contract.symbol}")

    #provides information on the execution of the order
    def execDetails(self, reqId, contract, execution):
        print(f"Execution Details: ID:{execution.orderId} || {execution.side} {execution.shares} {contract.symbol} @ {execution.time}")


    #calculates the volatility of the stock from given data to promote abstraction
    def calculateVolatilityFromData(self, df):
        log_returns = np.log(df['Close'] / df['Close'].shift(1))
        #calculate the annualized volatility
        volatility = log_returns.std() * np.sqrt(252)
        return volatility
    
    #calculate the volatility of the stock and attach it to the symbol
    def calculateVolatility(self, symbol):
        #reset the historical data list
        self.historicalData = []

        #request the symbol historical data and wait 5 seconds
        self.reqHistoricalData(
        reqId=1, 
        contract = Contract,
        endDateTime='', 
        durationStr='1 M', 
        barSizeSetting='1 day', 
        whatToShow='MIDPOINT', 
        useRTH=1, 
        formatDate=1, 
        keepUpToDate=False, 
        chartOptions=[]
    )
        time.sleep(5)

        df = pd.DataFrame(self.historicalData, columns = ['Date', 'Close'])
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        return self.calculate_volatility_from_data(df)


     # Calculate RSI
    # def calculateRSI(self, symbol, period=14):
    #     # Reset the historical data list
    #     self.historicalData = []

    #     # Request the symbol historical data and wait 5 seconds
    #     self.reqHistoricalData(symbol)
    #     time.sleep(5)

    #     # Create a DataFrame from the historical data
    #     df = pd.DataFrame(self.historicalData, columns=['Date', 'Close'])
    #     df['Date'] = pd.to_datetime(df['Date'])
    #     df.set_index('Date', inplace=True)

    #     # Calculate the RSI
    #     delta = df['Close'].diff()
    #     gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    #     loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    #     rs = gain / loss
    #     rsi = 100 - (100 / (1 + rs))

    #     return rsi


#create an instance of the reversionOfMeanApp class
app = reversionOfMeanApp()

symbol = "AAPL"

#Test the volatility calculation

Volatility = app.calculateVolatility(symbol)
print(f"The Volatility of {symbol} is: {Volatility}")