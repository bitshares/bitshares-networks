# pylint: disable=broad-except
"""
╔╗ ╦╔╦╗╔═╗╦ ╦╔═╗╦═╗╔═╗╔═╗  ╔╗╔╔═╗╔╦╗╦ ╦╔═╗╦═╗╦╔═╔═╗
╠╩╗║ ║ ╚═╗╠═╣╠═╣╠╦╝║╣ ╚═╗  ║║║║╣  ║ ║║║║ ║╠╦╝╠╩╗╚═╗
╚═╝╩ ╩ ╚═╝╩ ╩╩ ╩╩╚═╚═╝╚═╝  ╝╚╝╚═╝ ╩ ╚╩╝╚═╝╩╚═╩ ╩╚═╝

LIQUIDITY POOL MAPPER
"""

# STANDARD PYTHON MODULES
import time
from json import dumps as json_dumps
from json import loads as json_loads

# THIRD PARTY MODULES
from websocket import create_connection as wss

# LIQUIDITY POOL MAPPER MODULES
from config import NODES


def wss_handshake():
    """
    Create a websocket handshake
    """
    while True:
        nodes = NODES[::]
        nodes.append(nodes.pop(0))
        node = nodes[0]
        start = time.time()
        rpc = wss(node, timeout=3)
        if time.time() - start < 3:
            break
    return rpc


def wss_query(rpc, params):
    """
    Send and receive websocket requests
    """
    query = json_dumps({"method": "call", "params": params, "jsonrpc": "2.0", "id": 1})
    rpc.send(query)
    ret = json_loads(rpc.recv())
    try:
        ret = ret["result"]  # if there is result key take it
    except Exception:
        print(ret)
    return ret


def rpc_get_objects(rpc, object_ids):
    """
    Return data about objects in 1.7.x, 2.4.x, 1.3.x, etc. format
    """
    ret = wss_query(rpc, ["database", "get_objects", [object_ids]])
    return {object_ids[idx]: item for idx, item in enumerate(ret) if item is not None}


def rpc_ticker(rpc, pair):
    """
    RPC the latest ticker price
    ~
    :RPC param base: symbol name or ID of the base asset
    :RPC param quote: symbol name or ID of the quote asset
    :RPC returns: The market ticker for the past 24 hours
    """
    asset, currency = pair.split(":")
    ticker = wss_query(rpc, ["database", "get_ticker", [currency, asset, False]])
    return float(ticker["latest"])


def get_max_object(rpc, space):
    """
    get the maximum object id within this instance space
    using a modified exponential search
    allow for missing values
    """
    power = 5
    max_object = 0
    objects = []
    while True:
        ids = [f"{space}{int(max_object + i ** power)}" for i in range(1, 777)]
        try:
            objects = [
                int(v["id"].split(".")[2])
                for v in rpc_get_objects(rpc, ids).values()
                if v is not None
            ]
            max_object = max(objects)
            if len(objects) == 1:
                power -= 0.5
            if power < 1:
                break
        except Exception:
            power -= 0.5
    return max_object


def get_liquidity_pool_volume(rpc, pools):
    """
    get the sum amount a volume for a given set of liquidity pools
    """
    return {
        i["id"]: int(i["statistics"]["_24h_exchange_a2b_amount_a"])
        + int(i["statistics"]["_24h_exchange_b2a_amount_a"])
        for i in wss_query(
            rpc, ["database", "get_liquidity_pools", [pools, False, True]]
        )
    }


def rpc_get_feed(rpc, data_id):
    """
    return the oracle feed price for a given MPA
    """
    # given the bitasset_data_id, get the median feed price
    feed = rpc_get_objects(rpc, [data_id])[data_id]["median_feed"]["settlement_price"]
    # calculate the base feed amount in human terms
    base = int(feed["base"]["amount"])
    base_asset_id = feed["base"]["asset_id"]
    base_precision = int(
        rpc_get_objects(rpc, [base_asset_id])[base_asset_id]["precision"]
    )
    # calculate the quote feed amount in human terms
    quote = int(feed["quote"]["amount"])
    quote_asset_id = feed["quote"]["asset_id"]
    quote_precision = int(
        rpc_get_objects(rpc, [quote_asset_id])[quote_asset_id]["precision"]
    )
    # convert fractional human price to floating point
    return (base / 10**base_precision) / (quote / 10**quote_precision)
