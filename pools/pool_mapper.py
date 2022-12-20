# pylint: disable=too-many-locals, consider-using-f-string
"""
litepresence.com & squidKid-deluxe present:

╔╗ ╦╔╦╗╔═╗╦ ╦╔═╗╦═╗╔═╗╔═╗  ╔╗╔╔═╗╔╦╗╦ ╦╔═╗╦═╗╦╔═╔═╗
╠╩╗║ ║ ╚═╗╠═╣╠═╣╠╦╝║╣ ╚═╗  ║║║║╣  ║ ║║║║ ║╠╦╝╠╩╗╚═╗
╚═╝╩ ╩ ╚═╝╩ ╩╩ ╩╩╚═╚═╝╚═╝  ╝╚╝╚═╝ ╩ ╚╩╝╚═╝╩╚═╩ ╩╚═╝

LIQUIDITY POOL MAPPER

MIT License
"""

# STANDARD MODULES
import json
import math
from os import system
from os.path import exists
from shutil import rmtree

# THIRD PARTY MODULES
from pyvis.network import Network

# LIQUIDITY POOL MAPPER MODULES
from config import (
    DETACH,
    COLOR,
    BUTTONS,
    CHUNK,
    DARK_THEME,
    HEIGHT,
    SCALE_WEIGHT,
    DETACH_UNFUNDED,
    ATTACH,
)
from rpc import (
    wss_handshake,
    get_max_object,
    rpc_get_objects,
    rpc_ticker,
    get_liquidity_pool_volume,
    rpc_get_feed,
)
from utilities import chunks, json_ipc, dprint, logo, PATH, sigfig, NIL


def init_pipe():
    """
    Create the pipe files if they don't exist
    :return: None
    """
    if not exists(PATH):
        system(f"mkdir {PATH}")
    filenames = {
        "id_cache.txt": "[]",
        "name_cache.txt": "{}",
        "pool_cache.txt": "{}",
        "ticker_cache.txt": "{}",
        "share_cache.txt": "[]",
        "named_share_cache.txt": "{}",
    }
    for filename, initial_content in filenames.items():
        filepath = f"{PATH}/{filename}"
        if not exists(filepath):
            json_ipc(filename, initial_content)


def cache_pool_data(rpc):
    """
    some RPC calls can be done once, move them to disk
    :return: None
    """
    id_cache, data2 = [], []
    max_obj = get_max_object(rpc, space="1.19.")
    # for each object between 1.19.0 and 1.19.maxobj
    for obj in range(0, max_obj + 1, CHUNK):
        # read the id_cache
        id_cache = json_ipc("id_cache.txt")
        # only request this object if it is not already in the id_cache
        objs = [
            obj + addendum
            for addendum in range(CHUNK)
            if f"1.19.{obj + addendum}" not in id_cache
        ]
        # request a chunk of objects
        data = rpc_get_objects(rpc, [f"1.19.{o}" for o in objs])
        data2 = []
        share_cache = json_ipc("share_cache.txt")
        # read the pool id_cache
        pool_cache = json_ipc("pool_cache.txt")
        # for every object received from the call
        for key, value in data.items():
            # add the pool and its assets to the pool_cache, if not there already
            if key not in pool_cache:
                pool_cache[key] = {
                    "asset_a": value["asset_a"],
                    "asset_b": value["asset_b"],
                    "balance_a": int(value["balance_a"]),
                    "balance_b": int(value["balance_b"]),
                    "share_asset": value["share_asset"],
                }
            data2.extend((value["asset_a"], value["asset_b"]))
            share_cache.append(value["share_asset"])

        # asset ids found in this round
        data2 = list(set(data2))
        data2 = [f"1.3.{str(i)}" for i in sorted(int(i.split(".")[-1]) for i in data2)]
        # previously found asset ids
        id_cache = list(set(id_cache))
        id_cache = [
            f"1.3.{str(i)}" for i in sorted(int(i.split(".")[-1]) for i in id_cache)
        ]
        # all known asset ids in pools
        asset_ids = list(set(id_cache + data2))
        dprint("\nobj", obj)
        dprint("\ndata", data)
        dprint("\nobjs", objs)
        dprint("\ndata2", data2)
        dprint("\ncache", id_cache)
        # update the caches
        json_ipc("pool_cache.txt", pool_cache)
        json_ipc("id_cache.txt", asset_ids)
        json_ipc("share_cache.txt", share_cache)
    pool_cache = json_ipc("pool_cache.txt")
    dprint("\ncache + data2", id_cache + data2)
    dprint("\npool_cache", pool_cache)
    # sort the id id_cache
    id_cache = json_ipc("id_cache.txt")
    id_cache = [
        f"1.3.{str(i)}" for i in sorted(int(i.split(".")[-1]) for i in id_cache)
    ]
    # save to disk
    json_ipc("id_cache.txt", id_cache)


def cache_asset_name(rpc):
    """
    gather asset names and precisions; cache to disk
    :return: None
    """
    id_cache = json_ipc("id_cache.txt")
    share_cache = json_ipc("share_cache.txt")
    for idx, cache in enumerate([id_cache, share_cache]):
        cache_file = "named_share_cache.txt" if idx else "name_cache.txt"
        dprint("id_cache", cache)
        # chunk the id_cache into sections of 10
        cid = chunks(cache, len(cache) // 2)
        # iterate through each chunk
        for objs in cid:
            # load the asset id:name name_cache
            name_cache = json_ipc(cache_file)
            objs2 = [obj for obj in objs if obj not in name_cache]
            if objs2:
                data = rpc_get_objects(rpc, objs2)
                data2 = [
                    {"symbol": v["symbol"], "precision": v["precision"]}
                    for k, v in data.items()
                ]
                # update the name_cache
                json_ipc(cache_file, {**dict(zip(objs2, data2)), **name_cache})


def cache_weights(rpc):
    """
    ticker_cache will be used to scale the amounts in each pool
    back to BTS core token to visualize on equal terms
    :return: None
    """
    weights = []
    pool_cache = json_ipc("pool_cache.txt")
    name_cache = json_ipc("name_cache.txt")
    named_share_cache = json_ipc("named_share_cache.txt")
    ticker_cache = json_ipc("ticker_cache.txt")
    pools_chunked = chunks(list(pool_cache.keys()), 100)
    volumes = {}
    ticker_cache["1.3.0"] = 1
    for chunk in pools_chunked:
        volumes = {**volumes, **get_liquidity_pool_volume(rpc, chunk)}
    for pool, item in pool_cache.items():
        dprint(name_cache[item["asset_a"]])
        ticker = {"asset_a": 0, "asset_b": 0}
        for i in ["asset_a", "asset_b"]:
            # if the token is BTS, the ticker is 1
            if item[i] == "1.3.0":
                ticker[i] = 1
            elif item[i] in ticker_cache:
                ticker[i] = ticker_cache[item[i]]
            else:
                ticker[i] = rpc_ticker(rpc, f"1.3.0:{item[i]}")
                ticker_cache[item[i]] = ticker[i]
        ticker_a = ticker["asset_a"]
        ticker_b = ticker["asset_b"]
        precision_a = name_cache[item["asset_a"]]["precision"]
        precision_b = name_cache[item["asset_b"]]["precision"]
        balance_a = item["balance_a"]
        balance_b = item["balance_b"]
        volume_a = volumes[pool]
        dprint(ticker_cache)
        dprint("v0, v1", item["asset_a"], item["asset_b"])
        dprint("ticker_a, balance_a, precision_a")
        dprint(ticker_a, balance_a, precision_a)
        dprint("ticker_b, balance_b, precision_b")
        dprint(ticker_b, balance_b, precision_b)
        wt_balance = (
            ticker_a * balance_a / 10**precision_a
            + ticker_b * balance_b / 10**precision_b
        )
        wt_volume = ticker_a * volume_a / 10**precision_a
        human_balance_a = balance_a / 10**precision_a
        human_balance_b = balance_b / 10**precision_b
        price = human_balance_a / (human_balance_b + NIL)
        inverse = 1 / (price + NIL)
        # add the edge weights
        weights.append(
            {
                "asset_a": item["asset_a"],
                "asset_b": item["asset_b"],
                "wt_balance": math.log(wt_balance + 1),
                "wt_volume": math.log(wt_volume + 1),
                "pool_id": pool,
                "pool_name": named_share_cache[item["share_asset"]]["symbol"],
                "balance_a": human_balance_a,
                "balance_b": human_balance_b,
                "price": price,
                "inverse": inverse,
            }
        )

    json_ipc("ticker_cache.txt", ticker_cache)
    return weights


def map_network(rpc, weights, choice, is_balance):
    """
    build a pyvis network map of the BitShares Liquidity Pools
    :param weights: will be used for edge thickness
    :return:
    """
    name_cache = json_ipc("name_cache.txt")
    ticker_cache = json_ipc("ticker_cache.txt")
    usd_feed = rpc_get_feed(rpc, "2.4.294")
    btc_feed = rpc_get_feed(rpc, "2.4.295")
    bgcolor = "#222222" if DARK_THEME else "#888888"
    font_color = "#888888" if DARK_THEME else "#222222"

    node_colors = []
    for symbol in [i["symbol"] for i in name_cache.values()]:
        # re-declare the color map logic with a new symbol
        node_color_mapping = {
            COLOR[0]: "HONEST" in symbol,
            COLOR[1]: ("GDEX" in symbol) or (symbol in ["DEFI", "GAT"]),
            COLOR[2]: (symbol in ["GOLD", "SILVER", "CNY 1.0"]) or (len(symbol) == 3),
            COLOR[3]: ("BTWTY" in symbol) or ("TWENTIX" in symbol),
            COLOR[4]: "IOB" in symbol,
            COLOR[5]: "CRUDE" in symbol,
            COLOR[6]: "XBTSX" in symbol,
            COLOR[7]: symbol in ["NIUSHI", "NSNFT"],
            COLOR[8]: symbol in ["GOLDBACK", "QUINT", "BEOS"],
            COLOR[9]: True,
        }
        for color, condition in node_color_mapping.items():
            if condition:
                node_colors.append(color)
                break

    node_title = [
        "Value of {}:\n\nBTS: {:.3f}\nUSD: {:.3f}\nBTC: {:.3f}".format(
            symbol,
            1 / (ticker_cache[symbol] + NIL),
            1 / ((ticker_cache[symbol] + NIL) / usd_feed),
            1 / ((ticker_cache[symbol] + NIL) / btc_feed),
        )
        for symbol in name_cache.keys()
    ]
    net = Network(
        height=f"{HEIGHT}px",
        width="100%",
        bgcolor=bgcolor,
        font_color=font_color,
        select_menu=True,
    )
    net.add_nodes(
        list(name_cache.keys()),
        label=[i["symbol"] for i in list(name_cache.values())],
        color=node_colors,
        size=[10 for _ in name_cache],
        title=node_title,
    )
    net.add_node("", label="", image="./images/bitshares.png", size=500, shape="image", mass=0.5)
    net.add_node(" ", label="", image="./images/pool_network.png", size=100, shape="image", mass=0.7)
    dprint("\n\n")
    dprint(net.get_nodes())
    pool_cache = json_ipc("pool_cache.txt")
    # calculate max balance or volume weight based on user choice
    # at the same time, if user choice is 1 only ATTACH some weights
    max_w = max(
        n["wt_balance"] if is_balance else n["wt_volume"]
        for n in weights
        if choice != 1 or n["pool_id"] in ATTACH
    )
    dprint(max_w)
    max_w /= SCALE_WEIGHT
    for weight in weights:
        if all(
            [
                weight["asset_a"] in name_cache,
                weight["asset_b"] in name_cache,
                (not DETACH_UNFUNDED or weight["wt_balance"] > 0),
                (weight["asset_a"] not in DETACH or choice != 2),
                (weight["asset_b"] not in DETACH or choice != 2),
                ((weight["pool_id"] in ATTACH) or choice != 1),
            ]
        ):
            net.add_edge(
                weight["asset_a"],
                weight["asset_b"],
                value=weight["wt_balance"] / max_w if is_balance else weight["wt_volume"] / max_w,
                title="{}\n{} {}\n\n{} {}\n{} {}\n\nprice   {}\ninverse {}".format(
                    weight["pool_id"],
                    pool_cache[weight["pool_id"]]["share_asset"],
                    weight["pool_name"],
                    weight["asset_a"],
                    str(weight["balance_a"]),
                    weight["asset_b"],
                    str(weight["balance_b"]),
                    str(sigfig(weight["price"])),
                    str(sigfig(weight["inverse"])),
                ),
            )

    net.show_buttons(filter_=BUTTONS)
    net.show("liquidity_pools.html")


def initialize():
    """
    gather necessary data from disk or rpc as required
    :return: weights
    """
    init_pipe()
    rpc = wss_handshake()
    cache_pool_data(rpc)
    cache_asset_name(rpc)
    return cache_weights(rpc), rpc


def menu():
    """
    dispatch user choice
    """
    print(logo())
    dispatch = dict(
        enumerate(
            [
                "Full BitShares Pool Network",
                "ATTACH Configured Pools Only",
                "DETACH Configured Tokens",
                "Clear Cache",
            ]
        )
    )
    choice = get_choice(dispatch)
    print(logo())
    print("\nScale pool size in BTS terms by...")
    dispatch = dict(enumerate(["24hr Volume", "Total A + B Balance"]))
    is_balance = get_choice(dispatch)
    if choice == 3:
        # clear cache
        rmtree(PATH)
        system(f"mkdir {PATH}")
        main()
    return choice, is_balance


def get_choice(dispatch):
    """
    Prompt user with dispatch
    """
    print(json.dumps(dispatch, indent=4))
    result = input("\nEnter choice number:\n")
    result = int(result) if result else 0
    return result


def main():
    """
    initialize data via rpc and on disk cache
    then map the network
    :return:
    """
    print(logo())
    print("\n\nCaching data...")
    weights, rpc = initialize()
    choice, is_balance = menu()
    map_network(rpc, weights, choice, is_balance)


if __name__ == "__main__":
    main()
