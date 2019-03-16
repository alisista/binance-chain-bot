
import requests
import schedule
import time
import argparse
import getpass
import subprocess
import json
import sys
from pprint import pprint

EXECUTE_BNB_CLI = "./bnbcli"
NODE = " --node https://data-seed-pre-0-s1.binance.org:443 --trust-node"
CHAIN_ID = " --chain-id Binance-Chain-Nile"


class BinanceBot:

    def __init__(self, args):

        # basic information
        self.args = args
        self.symbol = args.symbol
        self.key = args.key

        # assets in my address
        self.amount_symbol = 0.0
        self.amount_bnb = 0.0

        # enemy bot information
        self.sell_quantity = 0.0
        self.sell_total_bnb = 0.0
        self.buy_quantity = 0.0
        self.buy_total_bnb = 0.0

        # order information
        self.depth = {"bids": [], "asks": []}
        self.selling_order_id = []
        self.buying_order_id = []

        # Get password from std input
        self.password = getpass.getpass()

        # Get address associated with input key
        self.address = get_address(self.key)

    def job(self):
        '''
            cron job
        '''

        # delete old orders
        self.delete_old_orders()

        # fetch the depth
        self.set_depth()

        # get info of enemy bot
        self.enemy_bot_info()

        # check my assets
        self.my_assets()

        # check price for bid and ask
        if self.args.more:
            bid_price, ask_price = self.more_earning_ask_bid
        else:
            bid_price, ask_price = self.simple_ask_bid

        # place order
        self.new_buying_order(bid_price, self.min_quantity)
        self.new_selling_order(ask_price, self.min_quantity)

    def delete_old_orders(self):
        
        # check orders
        old_orders = open_orders(self.address, self.symbol)["order"]
        if self.args.openOrders:
            pprint(old_orders)
        
        for old_order in old_orders:
            old_order_id = old_order["orderId"]

            if old_order_id in self.buying_order_id:
                print("delete old buying order: ", old_order_id)
                self.cancel_order(old_order_id)
                self.buying_order_id.remove(old_order_id)

            if old_order_id in self.selling_order_id:
                print("delete old selling order: ", old_order_id)
                self.cancel_order(old_order_id)
                self.selling_order_id.remove(old_order_id)

    def cancel_order(self, order_id):

        command = f"echo '{self.password}' | " + EXECUTE_BNB_CLI + \
                  f" dex cancel -l {self.symbol}_BNB -f {order_id}" \
                      f" --from {self.key} " + NODE + CHAIN_ID

        subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")

    def new_buying_order(self, price, amount):

        # not enough bnb
        if self.amount_bnb <= amount:
            return

        command = f"echo '{self.password}' | " + EXECUTE_BNB_CLI +\
                  f" dex order -l {self.symbol}_BNB -s 1 -p {int(round(price*1e8, -4))} -q {int(round(amount*1e8, -4))} " \
                  f" --from {self.key} " + NODE + CHAIN_ID

        proc = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")

        if proc.stdout.find("Id: ") >= 0:
            order_id = proc.stdout.split("Id: ")[1].split(", Symbol")[0]
            print("Buy:", price, amount, order_id)
            self.buying_order_id.append(order_id)
        else:
            sys.stderr.write(proc.stderr)
            sys.exit(1)

    def new_selling_order(self, price, amount):

        # not enough symbol token
        if self.amount_symbol <= amount:
            print("Without enough token, not possible to sell it.")
            return

        command = f"echo '{self.password}' | " + EXECUTE_BNB_CLI +\
                  f" dex order -l {self.symbol}_BNB -s 2 -p {int(round(price*1e8, -4))} -q {int(round(amount*1e8, -4))} " \
                  f" --from {self.key} " + NODE + CHAIN_ID

        proc = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
        if proc.stdout.find("Id: ") >= 0:
            order_id = proc.stdout.split("Id: ")[1].split(", Symbol")[0]
            print("Sell:", price, amount, order_id)
            self.selling_order_id.append(order_id)
        else:
            sys.stderr.write(proc.stderr)
            sys.exit(1)

    def enemy_bot_info(self):

        self.sell_quantity, self.sell_total_bnb, self.buy_quantity, self.buy_total_bnb = \
            check_sell_and_buy(self.symbol, n_show=int(self.args.showTrade))
        print("SELL:", self.sell_quantity, f'({self.sell_total_bnb} BNB)')
        print("BUY:", self.buy_quantity, f'({self.buy_total_bnb} BNB)')

    def my_assets(self):
        # Get amount of token that the address owns
        self.amount_symbol, self.amount_bnb = account_balance(self.address, self.symbol)

    def bot_pattern(self):
        # bot pattern 1: small amount of selling and buying
        if self.sell_quantity <= 1 and self.buy_quantity <= 1:
            print("bot pattern 1: small amount of selling and buying")

        # bot pattern 2: small buying and large selling
        elif self.sell_quantity > 1 >= self.buy_quantity:
            print("bot pattern 2: small buying and large selling")

        # bot pattern 3: large buying and small selling
        elif self.sell_quantity <= 1 < self.buy_quantity:
            print("bot pattern 3: large buying and small selling")

        # bot pattern 4: large selling and buying
        else:
            print("bot pattern 4: large selling and buying")

    def set_depth(self):
        self.depth = get_depth(self.symbol)
        if self.args.showDepth:
            pprint(self.depth)

    @property
    def simple_ask_bid(self):
        bid_price = round(float(self.depth["bids"][0][0]) + 0.001, 4)
        ask_price = round(float(self.depth["asks"][0][0]) - 0.001, 4)

        print("BID: ", bid_price, ", AMOUNT: ", self.min_quantity)
        print("ASK: ", ask_price, ", AMOUNT: ", self.min_quantity)
        return bid_price, ask_price

    @property
    def more_earning_ask_bid(self):

        bids = self.depth["bids"]
        asks = self.depth["asks"]
        bid_price = float(bids[0][0])
        ask_price = float(asks[0][0])

        number_of_bids = len(bids)

        for i, bid in enumerate(bids):
            amount_i = float(bid[1])

            # if you skip this bid, you loose amount_i,
            # but you can earn (price[i+1] - price[i])*quantity.
            if (float(bids[i+1][0]) - float(bid[0])) * amount_i > self.min_quantity:
                bid_price = float(bids[i+1][0]) + 0.001
            else:
                break

            if i > number_of_bids - 2:
                break

        number_of_asks = len(asks)

        for i, ask in enumerate(asks):
            amount_i = float(ask[1])

            # if you skip this bid, you loose amount_i,
            # but you can earn (price[i+1] - price[i])*quantity.
            if (float(ask[0]) - float(asks[i + 1][0])) * amount_i > self.min_quantity:
                bid_price = float(asks[i + 1][0]) - 0.001
            else:
                break

            if i > number_of_asks - 2:
                break

        print("BID: ", bid_price, ", AMOUNT: ", self.min_quantity)
        print("ASK: ", ask_price, ", AMOUNT: ", self.min_quantity)
        return bid_price, ask_price

    @property
    def min_quantity(self):
        quantity = min(self.sell_quantity, self.buy_quantity)
        return min(quantity, self.args.max)


def open_orders(address, symbol):
    return requests.get("https://testnet-dex.binance.org/api/v1/orders/open",
                        params={"address": address, "symbol": symbol + "_BNB"}).json()


def get_address(key):
    '''
    Get address stored in bnbcli
    :param key: key stored in bnbcli
    :return address: address stored in bnbcli
    '''
    command = EXECUTE_BNB_CLI + " keys show " + key
    proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, encoding="utf-8")
    address = proc.stdout.readlines()[1].split()[2]
    return address


def account_balance(address, symbol):
    '''
    Get amount of token in the address specified in param
    :param address: address of binance-chain
    :param symbol: symbol of token
    :return: amount of token that the address owns (symbol and BNB)
    '''

    command = EXECUTE_BNB_CLI + " account " + address + NODE + CHAIN_ID
    proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")

    assets = json.loads(proc.stdout.readlines()[0])
    coins = assets["value"]["base"]["coins"]

    amount_symbol = [coin["amount"] for coin in coins if coin["denom"] == symbol]
    amount_bnb = [coin["amount"] for coin in coins if coin["denom"] == "BNB"]

    amount_symbol = 0 if not amount_symbol else int(amount_symbol[0])
    amount_bnb = 0 if not amount_bnb else int(amount_bnb[0])

    return amount_symbol, amount_bnb


def check_sell_and_buy(symbol, n_show=0):
    '''
    Check sell and buy amount in the last bot action
    :param symbol: symbol of token
    :return: quantity and total bnb of selling and buying action
    '''

    trades = requests.get("https://testnet-dex.binance.org/api/v1/trades", params={"symbol": symbol + "_BNB", "limit": 200}).json()
    trades = trades["trade"]
    time_0 = trades[0]["time"]

    recent_trades = []  # collect recent trades

    for trade in trades:

        # Check if tradeId is zero, otherwise skip
        trade_id = trade["tradeId"]
        if trade_id.split("-")[1] != '0':
            continue

        if time_0 - trade["time"] >= 180000:  # more than 3 mins
            break
        else:

            recent_trades.append(trade)

    trades = recent_trades  # update trades

    if not trades:
        return 0, 0, 0, 0

    # Show trade
    if n_show > 0:
        for trade in zip(trades, range(n_show)):
            pprint(trade)

    seller_id = min(trades, key=lambda x: x["price"])["sellerId"]  # seller of min price
    buyer_id = max(trades, key=lambda x: x["price"])["buyerId"]  # buyer of max price

    sell_quantity = round(sum([float(t["quantity"]) for t in trades if t["sellerId"] == seller_id]), 4)
    buy_quantity = round(sum([float(t["quantity"]) for t in trades if t["buyerId"] == buyer_id]), 4)

    sell_total_bnb = round(sum([float(t["quantity"])*float(t["price"]) for t in trades if t["sellerId"] == seller_id]), 4)
    buy_total_bnb = round(sum([float(t["quantity"])*float(t["price"]) for t in trades if t["buyerId"] == buyer_id]), 4)

    return sell_quantity, sell_total_bnb, buy_quantity, buy_total_bnb


def get_depth(symbol):
    return requests.get("https://testnet-dex.binance.org/api/v1/depth", params={"symbol": symbol + "_BNB", "limit": 20}).json()


def main():

    parser = argparse.ArgumentParser(description='Binance-chain very simple bot')
    parser.add_argument('key', help='specify key in bnbcli')
    parser.add_argument('symbol', help='specify symbol')
    parser.add_argument('--showTrade', action="store", default=0, help="show n(int) number of trades")
    parser.add_argument('--showDepth', action="store_true", default=False, help="show depth (bids and asks)")
    parser.add_argument('--schedule', action="store", default=0, help="schedule job in every n(int) second")
    parser.add_argument('--openOrders', action="store_true", default=False, help="show open orders")
    parser.add_argument('--more', action="store_true", default=False, help="mode: more earning")
    parser.add_argument('--max', action="store", default=100, help="max quantity to buy")

    # Set arguments to variables
    args = parser.parse_args()

    bb = BinanceBot(args)

    if args.openOrders:
        pprint(open_orders(bb.address, bb.symbol))

    # execute only one time
    if args.schedule == 0:
        bb.job()

    # schedule job
    elif int(args.schedule) > 0:
        n = int(args.schedule)
        # schedule job for every n sec
        schedule.every(n).seconds.do(bb.job)

        while True:
            schedule.run_pending()
            time.sleep(1)

    else:
        return


if __name__ == "__main__":
    main()
