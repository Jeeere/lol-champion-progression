from distutils.log import error
from operator import truediv
import requests
import json
import sqlite3
from sqlite3 import Error
import time

# Addresses for needed tabs
loot_addr = "/lol-loot/v1/player-loot"
store_addr = "/lol-store/v1/champions"

# Initialize output dictionary
meme = {
    "player":{

    },
    "champions":{
        "total":0,
        "owned":0,
        "unique_shards":0
    }
}

# Initialize list for unowned champion shards
unowned_shards = []

champions_amounts = {
    "450":0,
    "1350":0,
    "3150":0,
    "4800":0,
    "6300":0,
    "7800":0,
}

history = "lol_progress.json"

def set_path(file):
    """
    Set League of Legends installation path
    """
    with open(file, "r+") as f:
        path = input("Input path to League of Legends installation directory: ")
        # Convert to fit JSON
        path = path.replace("\\", "/")
        # Parse JSON and dump path
        obj = json.load(f)
        obj["path"] = path
        f.seek(0)
        json.dump(obj, f)

def get_path(file):
    """
    Get League of Legends installation path
    """
    with open(file, "r") as f:
        obj = json.load(f)
        return obj["path"]

def set_last_insert(file):
    """
    Set timestamp of last database insert
    """
    with open(file, "r+") as f:
        obj = json.load(f)
        json_array = obj["times"]

        # If no entries in array
        if len(json_array) == 0:
            json_array.append({"accountId": meme["player"]["accountId"], "time": int(time.time())})
        else:
            # Loop over entries
            for json_object in json_array:

                # If entry contains current accountId
                if json_object["accountId"] == meme["player"]["accountId"]:
                    # Update time and dump
                    json_object["time"] = int(time.time())
                    f.seek(0)
                    json.dump(json_array, f)
                    return

            # Account not in file, append it
            json_array.append({"accountId": meme["player"]["accountId"], "time": int(time.time())})
        # Set array as value and dump
        obj["times"] = json_array
        f.seek(0)
        json.dump(obj, f)

def get_last_insert(file):
    """
    Get timestamp of last database insert
    """
    with open(file, "r") as f:
        json_array = json.load(f)["times"]
        for json_object in json_array:
            if json_object["accountId"] == meme["player"]["accountId"]:
                return int(json_object["time"])

def check_entry(last):
    """
    Checks if enough time has passed after last insert
    """
    now = int(time.time())
    delta = now - last
    if delta >= 86400:
        return True
    else:
        print("Less than one day from last insert. Not inserting data.")
        return False

def loot(url, credentials):
    """
    Handle data from loot tab
    """
    # Get response and parse JSON
    response = requests.get(url + loot_addr, verify = False, auth = credentials)
    json_array = json.loads(response.text)

    # Loop through loot
    for json_object in json_array:
        # If item is a champion
        if json_object["displayCategories"] == "CHAMPION":
            # Increase total disenchant value and total value
            meme["total_disenchant"] = meme.get("total_disenchant", 0) + (json_object["count"] * json_object["disenchantValue"])
            meme["total_value"] = meme.get("total_value", 0) + (json_object["count"] * json_object["value"])

            # If champion is unowned
            if json_object["itemStatus"] != "OWNED":
                # Increase total upgrade cost
                meme["total_upgrade_cost"] = meme.get("total_upgrade_cost", 0) + json_object["upgradeEssenceValue"]
                # Disenchant duplicate shards
                meme["disenchant_duplicates"] = meme.get("disenchant_duplicates", 0) + ((json_object["count"] - 1) * json_object["disenchantValue"])
                # Append champion name to unowned shards list
                unowned_shards.append(json_object["itemDesc"])
            else:
                # Disenchant owned shards
                meme["disenchant_duplicates"] = meme.get("disenchant_duplicates", 0) + (json_object["count"] * json_object["disenchantValue"])

    return True

def store(url, credentials):
    """
    Handle data from store tab
    """
    # Get response and parse JSON
    response = requests.get(url + store_addr, verify = False, auth = credentials)
    json_object = json.loads(response.text)

    # Get account details
    player = json_object["player"]
    meme["player"].update({"accountId": player["accountId"], "current_be": player["ip"], "current_rp": player["rp"], "summonerLevel": player["summonerLevel"]})

    # Loop over champions in store
    for champion in json_object["catalog"]:
        # Increase total amount of champions
        meme["champions"]["total"] = meme["champions"].get("total", 0) + 1
        # Increase total BE and RP costs
        meme["cost_all_rp"] = meme.get("cost_all_rp", 0) + champion["rp"]
        meme["cost_all_be"] = meme.get("cost_all_be", 0) + champion["ip"]

        # Get amount of champions per value
        get_champions_per_value(champion['ip'])

        # If champion is unowned
        if "owned" not in champion:
            # Increase unowned costs
            meme["cost_unowned_be"] = meme.get("cost_unowned_be", 0) + champion["ip"]
            meme["cost_unowned_rp"] = meme.get("cost_unowned_rp", 0) + champion["rp"]

            # If does not own champion shard
            if champion["name"] not in unowned_shards:
                # Increase costs for champions missing champion shard in loot
                meme["cost_missing_shard_be"] = meme.get("cost_missing_shard_be", 0) + champion["ip"]
                meme["cost_missing_shard_rp"] = meme.get("cost_missing_shard_rp", 0) + champion["rp"]
            else:
                # Increase amount of unique unowned champion shards
                meme["champions"]["unique_shards"] = meme["champions"].get("unique_shards", 0) + 1
        else:
            # Increase amount of owned champions
            meme["champions"]["owned"] = meme["champions"].get("owned", 0) + 1
    
    return True

def get_be_needed():
    """
    Calculate BE required to purchase all champions
    """
    total_cost = meme["total_upgrade_cost"] + meme["cost_missing_shard_be"]
    missing = total_cost - (meme["player"]["current_be"] + meme["disenchant_duplicates"])

    return missing

def get_rnd_champ_value():
    """
    Get average disenchant value of random champion shard
    """
    avg_champ_shard = ((champions_amounts['4800'] * 4800 + champions_amounts["6300"] * 6300 + champions_amounts["7800"] * 7800) * 0.2) / (champions_amounts['4800'] + champions_amounts["6300"] + champions_amounts["7800"])
    
    return avg_champ_shard


def get_champions_per_value(cost):
    """
    Increment champion amounts dictionary value by 1
    """
    # If champion value is 450, increment value by 1
    # Repeat for all values
    if cost == 450:
        champions_amounts["450"] = champions_amounts.get("450", 0) + 1
    elif cost == 1350:
        champions_amounts["1350"] = champions_amounts.get("1350", 0) + 1
    elif cost == 3150:
        champions_amounts["3150"] = champions_amounts.get("3150", 0) + 1
    elif cost == 4800:
        champions_amounts["4800"] = champions_amounts.get("4800", 0) + 1
    elif cost == 6300:
        champions_amounts["6300"] = champions_amounts.get("6300", 0) + 1
    elif cost == 7800:
        champions_amounts["7800"] = champions_amounts.get("7800", 0) + 1

    return True

def create_connection(db_file):
    """
    create a database connection to a SQLite database
    """
    conn = None
    try:
        conn = sqlite3.connect(db_file)
    except Error as e:
        print(e)
    else:
        cursor = conn.cursor()

        sql ='''
            CREATE TABLE IF NOT EXISTS PROGRESSION(
            ACCOUNT INTEGER NOT NULL,
            TIMESTAMP INTEGER NOT NULL,
            LEVEL INTEGER,
            BLUE_ESSENCE INTEGER,
            TOTAL_CHAMPIONS INTEGER,
            OWNED_CHAMPIONS INTEGER,
            UNIQUE_CHAMPION_SHARDS INTEGER,
            COST_UNOWNED INTEGER,
            COST_MISSING_SHARD INTEGER,
            DISENCHANT_DUPLICATES INTEGER,
            PRIMARY KEY (ACCOUNT, TIMESTAMP)
            )'''

        cursor.execute(sql)
        conn.commit()
        cursor.close()

        return conn

def insert_data(conn, data):
    """
    Insert data into db
    """
    sql = '''
        INSERT INTO PROGRESSION(
        ACCOUNT, TIMESTAMP, LEVEL, BLUE_ESSENCE, TOTAL_CHAMPIONS, OWNED_CHAMPIONS, UNIQUE_CHAMPION_SHARDS, COST_UNOWNED, COST_MISSING_SHARD, DISENCHANT_DUPLICATES
        ) VALUES (
        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )'''
    cursor = conn.cursor()
    cursor.execute(sql, data)
    conn.commit()
    cursor.close()
    set_last_insert(history)
    print("Data inserted to database")

    return cursor.lastrowid

def create_insertfile(file):
    """
    Create file containing League of Legends installation path and timestamps for last insert of each account
    """
    try:
        f = open(file, "x")
        f.close()
    except FileExistsError:
        return
    else:
        with open(file, "r+") as f:
            f.write(r'{"path": "C:/Riot Games/League of Legends", "times": []}')

def main():
    url = "https://127.0.0.1:"
    create_insertfile(history)
    try:
        lockfile_path = get_path(history)
        if lockfile_path == "":
            print("Empty path")
            set_path(history)
            main()
    except (FileNotFoundError, IndexError):
        print("Path file does not exist")
        set_path(history)
        main()

    try:
        with open(lockfile_path + r"/lockfile", "r") as f:
            data = f.read()
    except (FileNotFoundError, OSError):
        print("Incorrect path or League of Legends client not open")
        set_path(history)
        main()
    else:
        data = data.split(":")
        # Add port to url
        url += data[2]
        # Get password
        password = data[3]
        auth = ("riot", password)

        loot(url, auth)
        store(url, auth)
        print(meme)

        conn = create_connection("lol_account_progression.db")
        last = get_last_insert(history)
        # If first time
        if last == None:
            last = 0
        with conn:
            if check_entry(last):
                data = (meme["player"]["accountId"], int(time.time()), meme["player"]["summonerLevel"], meme["player"]["current_be"], meme["champions"]["total"], meme["champions"]["owned"], meme["champions"]["unique_shards"], meme["cost_unowned_be"], meme["cost_missing_shard_be"], meme["disenchant_duplicates"])
                insert_data(conn, data)

        print("Random champion shard average value: " + str(get_rnd_champ_value()))
        print("Total BE from disenchanting: " + str(meme["total_disenchant"]))
        print("Total BE from disenchanting duplicates: " + str(meme["disenchant_duplicates"]))
        print("Total BE value: " + str(meme["total_value"]))
        print("BE to upgrade all unowned champion shards: " + str(meme["total_upgrade_cost"]))
        
        print("BE to buy all from store: " + str(meme["cost_all_be"]))
        # print("RP cost to buy all from store: " + str(cost_all_rp))
        print("BE to buy unowned from store: " + str(meme["cost_unowned_be"]))
        # print("RP cost to buy unwoned from store: " + str(cost_unowned_rp))
        print("BE to buy champions missing shard from store: " + str(meme["cost_missing_shard_be"]))
        # print("RP cost to buy champions missing shard from store: " + str(cost_missing_shard_rp))

        print(str(meme["champions"]["owned"]) + "/" + str(meme["champions"]["total"]) + " champions owned")
        print(str(meme["champions"]["owned"] + meme["champions"]["unique_shards"]) + "/" + str(meme["champions"]["total"]) + " shards/champions owned")
        print("Missing " + str(get_be_needed()) + " BE to purchase all champions")

        conn.close()

if __name__ == "__main__":
    main()