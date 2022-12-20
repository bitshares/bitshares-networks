# pylint: disable=too-many-branches, too-many-statements, broad-except
"""
╔╗ ╦╔╦╗╔═╗╦ ╦╔═╗╦═╗╔═╗╔═╗  ╔╗╔╔═╗╔╦╗╦ ╦╔═╗╦═╗╦╔═╔═╗
╠╩╗║ ║ ╚═╗╠═╣╠═╣╠╦╝║╣ ╚═╗  ║║║║╣  ║ ║║║║ ║╠╦╝╠╩╗╚═╗
╚═╝╩ ╩ ╚═╝╩ ╩╩ ╩╩╚═╚═╝╚═╝  ╝╚╝╚═╝ ╩ ╚╩╝╚═╝╩╚═╩ ╩╚═╝

LIQUIDITY POOL MAPPER
"""

# STANDARD MODULES
import contextlib
import math
from os.path import dirname, abspath
import os
import time
import traceback
from json import dumps as json_dumps
from json import loads as json_loads

# LIQUIDITY POOL MAPPER MODULES
from config import DEV

# GLOBAL CONSTANTS
PATH = f"{dirname(abspath(__file__))}/pipe"
NIL = 1 / 10**16


def sigfig(number, precision=6):
    """
    :usage: print([sigfig(123456.789, i) for i in range(1, 10)])
    :param float(number):
    :param int(precision):
    :return:
    """
    return (
        round(
            round(number / (10 ** int(math.log(abs(number), 10))), precision - 1)
            * (10 ** int(math.log(abs(number), 10))),
            precision + 1,
        )
        if number
        else 0
    )


def logo():
    """
    ╔╗ ╦╔╦╗╔═╗╦ ╦╔═╗╦═╗╔═╗╔═╗  ╔╗╔╔═╗╔╦╗╦ ╦╔═╗╦═╗╦╔═╔═╗
    ╠╩╗║ ║ ╚═╗╠═╣╠═╣╠╦╝║╣ ╚═╗  ║║║║╣  ║ ║║║║ ║╠╦╝╠╩╗╚═╗
    ╚═╝╩ ╩ ╚═╝╩ ╩╩ ╩╩╚═╚═╝╚═╝  ╝╚╝╚═╝ ╩ ╚╩╝╚═╝╩╚═╩ ╩╚═╝

    LIQUIDITY POOL MAPPER
    """
    return "\033c" + logo.__doc__


def dprint(*args, **kwargs):
    """
    wraps print to only execute when config.py DEV is true
    """
    if DEV:
        print(*args, **kwargs)


def chunks(list1, n_chunks):
    """
    Yield n number of striped chunks from l
    """
    return [list1[i + 1 :: n_chunks] for i in range(-1, n_chunks)]


def json_ipc(doc="", text="", initialize=False, append=False):
    """
    JSON IPC

    Concurrent Interprocess Communication via Read and Write JSON

    features to mitigate race condition:

        open file using with statement
        explicit close() in with statement
        finally close()
        json formatting required
        postscript clipping prevents misread due to overwrite without erase
        read and write to the text pipe with a single definition
        growing delay between attempts prevents cpu leak

    to view your live streaming database, navigate to the pipe folder in the terminal:

        tail -F your_json_ipc_database.txt

    :dependencies: os, traceback, json.loads, json.dumps
    :warn: incessant read/write concurrency may damage older spinning platter drives
    :warn: keeping a 3rd party file browser pointed to the pipe folder may consume RAM
    :param str(doc): name of file to read or write
    :param str(text): json dumped list or dict to write; if empty string: then read
    :return: python list or dictionary if reading, else None

    wtfpl2020 litepresence.com
    """
    # initialize variables
    data = None
    # file operation type for exception message
    if text:
        act = "appending" if append else "writing"
    else:
        act = "reading"
    tag = "<<< JSON IPC >>>" if act != "appending" else ""
    # ensure we're writing json then add prescript and postscript for clipping
    try:
        if isinstance(text, (dict, list)):
            text = json_dumps(text)
        text = tag + json_dumps(json_loads(text)) + tag if text else text
    except:
        print(text)
        raise
    # move append operations to the comptroller folder and add new line
    if append:
        text = "\n" + text
    # create the pipe subfolder
    if initialize:
        os.makedirs(PATH, exist_ok=True)
        # ~ os.makedirs(PATH + "/comptroller", exist_ok=True)
    if doc:
        doc = f"{PATH}/{doc}"
        # race read/write until satisfied
        iteration = 0
        while True:
            # increment the delay between attempts exponentially
            time.sleep(0.02 * iteration**2)
            try:
                if act == "appending":
                    with open(doc, "a", encoding="utf-8") as handle:
                        handle.write(text)
                        handle.close()
                        break
                elif act == "reading":
                    with open(doc, "r", encoding="utf-8") as handle:
                        # only accept legitimate json
                        data = json_loads(handle.read().split(tag)[1])
                        handle.close()
                        break
                elif act == "writing":
                    with open(doc, "w+", encoding="utf-8") as handle:
                        handle.write(text)
                        handle.close()
                        break
            except Exception:
                if iteration == 1:
                    if "json_ipc" in text:
                        print("no json_ipc pipe found, initializing...")
                    else:
                        print(  # only if it happens more than once
                            iteration,
                            f"json_ipc failed while {act} to {doc} retrying...\n",
                        )
                elif iteration == 10:
                    print("json_ipc unexplained failure\n", traceback.format_exc())
                elif iteration == 5:
                    # maybe there is no pipe? auto initialize the pipe!
                    json_ipc(initialize=True)
                    print("json_ipc pipe initialized, retrying...\n")
                iteration += 1
                continue
            finally:
                with contextlib.suppress(Exception):
                    handle.close()
    return data
