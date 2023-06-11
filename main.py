"""Main file"""
import json
import time
import sqlite3
from sqlite3 import Error

import requests

# Addresses for needed tabs
LOOT_ADDR = "/lol-loot/v1/player-loot"
STORE_ADDR = "/lol-store/v1/champions"
# History file
HISTORY = "lol_progress.json"
# Initialize output dictionary
OUTPUT = {
    "player": {},
    "champions": {"total": 0, "owned": 0, "unique_shards": 0},
    "total_upgrade_cost": 0,
    "cost_unowned_be": 0,
    "cost_missing_shard_be": 0,
}
# Initialize list for unowned champion shards
unowned_shards = []
champions_amounts = {
    "450": 0,
    "1350": 0,
    "3150": 0,
    "4800": 0,
    "6300": 0,
    "7800": 0,
}


def set_path(file_path):
    """
    Set League of Legends installation path
    """
    path = input("Input path to League of Legends installation directory: ")
    # Convert to fit JSON
    path = path.replace("\\", "/")

    with open(file_path, "r", encoding="utf-8") as file:
        # Parse JSON
        obj = json.load(file)

    obj["path"] = path

    with open(file_path, "w", encoding="utf-8") as file:
        # Dump updated JSON
        json.dump(obj, file)


def get_path(path):
    """
    Get League of Legends installation path
    """
    with open(path, "r", encoding="utf-8") as file:
        try:
            obj = json.load(file)
            return obj["path"]
        except json.decoder.JSONDecodeError as error:
            print("Error decoding history!")
            print(error)
            return -1


def set_last_insert(path):
    """
    Set timestamp of last database insert
    """
    with open(path, "r", encoding="utf-8") as file:
        obj = json.load(file)

    json_array = obj["times"]

    # If no entries in array
    if len(json_array) == 0:
        json_array.append(
            {"accountId": OUTPUT["player"]["accountId"], "time": int(time.time())}
        )
    else:
        # Loop over entries
        for json_object in json_array:
            # If entry contains current accountId
            if json_object["accountId"] == OUTPUT["player"]["accountId"]:
                # Update time and dump
                json_object["time"] = int(time.time())

                with open(path, "w", encoding="utf-8") as file:
                    obj["times"] = json_array
                    json.dump(obj, file)
                return

        # Account not in file, append it
        json_array.append(
            {"accountId": OUTPUT["player"]["accountId"], "time": int(time.time())}
        )
    # Set array as value and dump
    with open(path, "w", encoding="utf-8") as file:
        obj["times"] = json_array
        json.dump(obj, file)


def get_last_insert(path):
    """
    Get timestamp of last database insert
    """
    with open(path, "r", encoding="utf-8") as file:
        json_array = json.load(file)["times"]
        for json_object in json_array:
            if json_object["accountId"] == OUTPUT["player"]["accountId"]:
                return int(json_object["time"])
    return -1


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
    response = requests.get(url + LOOT_ADDR, verify=False, auth=credentials, timeout=10)
    json_array = json.loads(response.text)

    # Loop through loot
    for json_object in json_array:
        # If item is a champion
        if json_object["displayCategories"] == "CHAMPION":
            # Increase total disenchant value and total value
            OUTPUT["total_disenchant"] = OUTPUT.get("total_disenchant", 0) + (
                json_object["count"] * json_object["disenchantValue"]
            )
            OUTPUT["total_value"] = OUTPUT.get("total_value", 0) + (
                json_object["count"] * json_object["value"]
            )

            # If champion is unowned
            if json_object["itemStatus"] != "OWNED":
                # Increase total upgrade cost
                OUTPUT["total_upgrade_cost"] = (
                    OUTPUT.get("total_upgrade_cost", 0)
                    + json_object["upgradeEssenceValue"]
                )
                # Disenchant duplicate shards
                OUTPUT["disenchant_duplicates"] = OUTPUT.get(
                    "disenchant_duplicates", 0
                ) + ((json_object["count"] - 1) * json_object["disenchantValue"])
                # Append champion name to unowned shards list
                unowned_shards.append(json_object["itemDesc"])
            else:
                # Disenchant owned shards
                OUTPUT["disenchant_duplicates"] = OUTPUT.get(
                    "disenchant_duplicates", 0
                ) + (json_object["count"] * json_object["disenchantValue"])

    return True


def store(url, credentials):
    """
    Handle data from store tab
    """
    # Get response and parse JSON
    response = requests.get(
        url + STORE_ADDR, verify=False, auth=credentials, timeout=10
    )
    json_object = json.loads(response.text)

    # Get account details
    player = json_object["player"]
    OUTPUT["player"].update(
        {
            "accountId": player["accountId"],
            "current_be": player["ip"],
            "current_rp": player["rp"],
            "summonerLevel": player["summonerLevel"],
        }
    )

    # Loop over champions in store
    for champion in json_object["catalog"]:
        # Increase total amount of champions
        OUTPUT["champions"]["total"] = OUTPUT["champions"].get("total", 0) + 1
        # Increase total BE and RP costs
        OUTPUT["cost_all_rp"] = OUTPUT.get("cost_all_rp", 0) + champion["rp"]
        OUTPUT["cost_all_be"] = OUTPUT.get("cost_all_be", 0) + champion["ip"]

        # Get amount of champions per value
        get_champions_per_value(champion["ip"])

        # If champion is unowned
        if "owned" not in champion:
            # Increase unowned costs
            OUTPUT["cost_unowned_be"] = (
                OUTPUT.get("cost_unowned_be", 0) + champion["ip"]
            )
            OUTPUT["cost_unowned_rp"] = (
                OUTPUT.get("cost_unowned_rp", 0) + champion["rp"]
            )

            # If does not own champion shard
            if champion["name"] not in unowned_shards:
                # Increase costs for champions missing champion shard in loot
                OUTPUT["cost_missing_shard_be"] = (
                    OUTPUT.get("cost_missing_shard_be", 0) + champion["ip"]
                )
                OUTPUT["cost_missing_shard_rp"] = (
                    OUTPUT.get("cost_missing_shard_rp", 0) + champion["rp"]
                )
            else:
                # Increase amount of unique unowned champion shards
                OUTPUT["champions"]["unique_shards"] = (
                    OUTPUT["champions"].get("unique_shards", 0) + 1
                )
        else:
            # Increase amount of owned champions
            OUTPUT["champions"]["owned"] = OUTPUT["champions"].get("owned", 0) + 1

    return True


def get_be_needed():
    """
    Calculate BE required to purchase all champions
    """
    total_cost = OUTPUT["total_upgrade_cost"] + OUTPUT["cost_missing_shard_be"]
    missing = total_cost - (
        OUTPUT["player"]["current_be"] + OUTPUT["disenchant_duplicates"]
    )

    return missing


def get_rnd_champ_value():
    """
    Get average disenchant value of random champion shard
    """
    avg_champ_shard = (
        (
            champions_amounts["4800"] * 4800
            + champions_amounts["6300"] * 6300
            + champions_amounts["7800"] * 7800
        )
        * 0.2
    ) / (
        champions_amounts["4800"]
        + champions_amounts["6300"]
        + champions_amounts["7800"]
    )

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
    except Error as error:
        print(error)
        return -1

    cursor = conn.cursor()

    sql = """
        CREATE TABLE IF NOT EXISTS PROGRESSION(
        ACCOUNT INTEGER NOT NULL,
        TIMESTAMP INTEGER NOT NULL,
        LEVEL INTEGER,
        TOTAL_CHAMPIONS INTEGER,
        OWNED_CHAMPIONS INTEGER,
        UNIQUE_CHAMPION_SHARDS INTEGER,
        BLUE_ESSENCE INTEGER,
        DISENCHANT_DUPLICATES INTEGER,
        COST_UNOWNED INTEGER,
        COST_MISSING_SHARD INTEGER,
        COST_UPGRADE INTEGER,
        PRIMARY KEY (ACCOUNT, TIMESTAMP)
        )"""

    cursor.execute(sql)
    conn.commit()
    cursor.close()

    return conn


def insert_data(conn, data):
    """
    Insert data into db
    """
    sql = """
        INSERT INTO PROGRESSION(
        ACCOUNT, TIMESTAMP, LEVEL, TOTAL_CHAMPIONS, OWNED_CHAMPIONS, UNIQUE_CHAMPION_SHARDS, BLUE_ESSENCE, DISENCHANT_DUPLICATES, COST_UNOWNED, COST_MISSING_SHARD, COST_UPGRADE
        ) VALUES (
        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )"""
    cursor = conn.cursor()
    cursor.execute(sql, data)
    conn.commit()
    cursor.close()
    set_last_insert(HISTORY)
    print("Data inserted to database")

    return cursor.lastrowid


def create_insertfile(path):
    """
    Create file containing League of Legends installation'
    path and timestamps for last insert of each account.
    """
    try:
        file = open(path, "x", encoding="utf-8")
        file.close()
    except FileExistsError:
        return
    else:
        with open(path, "r+", encoding="utf-8") as file:
            file.write(r'{"path": "C:/Riot Games/League of Legends", "times": []}')


def main():
    """
    Main function.
    """
    url = "https://127.0.0.1:"
    create_insertfile(HISTORY)
    try:
        lockfile_path = get_path(HISTORY)
        if lockfile_path == "":
            print("Empty path")
            set_path(HISTORY)
            main()
    except (FileNotFoundError, IndexError, json.decoder.JSONDecodeError):
        print("Path file does not exist")
        set_path(HISTORY)
        main()

    try:
        with open(lockfile_path + r"/lockfile", "r", encoding="utf-8") as file:
            data = file.read()
    except (FileNotFoundError, OSError):
        print("Incorrect path or League of Legends client not open")
        set_path(HISTORY)
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
        print(OUTPUT)

        conn = create_connection("lol_account_progression.db")
        last = get_last_insert(HISTORY)
        # If first time
        if last is None:
            last = 0
        with conn:
            if check_entry(last):
                data = (
                    OUTPUT["player"]["accountId"],
                    int(time.time()),
                    OUTPUT["player"]["summonerLevel"],
                    OUTPUT["champions"]["total"],
                    OUTPUT["champions"]["owned"],
                    OUTPUT["champions"]["unique_shards"],
                    OUTPUT["player"]["current_be"],
                    OUTPUT["disenchant_duplicates"],
                    OUTPUT["cost_unowned_be"],
                    OUTPUT["cost_missing_shard_be"],
                    OUTPUT["total_upgrade_cost"],
                )
                insert_data(conn, data)

        print("Random champion shard average value: " + str(get_rnd_champ_value()))
        print("Total BE from disenchanting: " + str(OUTPUT["total_disenchant"]))
        print(
            "Total BE from disenchanting duplicates: "
            + str(OUTPUT["disenchant_duplicates"])
        )
        print("Total BE value: " + str(OUTPUT["total_value"]))
        print(
            "BE to upgrade all unowned champion shards: "
            + str(OUTPUT["total_upgrade_cost"])
        )

        print("BE to buy all from store: " + str(OUTPUT["cost_all_be"]))
        # print("RP cost to buy all from store: " + str(cost_all_rp))
        print("BE to buy unowned from store: " + str(OUTPUT["cost_unowned_be"]))
        # print("RP cost to buy unwoned from store: " + str(cost_unowned_rp))
        print(
            "BE to buy champions missing shard from store: "
            + str(OUTPUT["cost_missing_shard_be"])
        )
        # print("RP cost to buy champions missing shard from store: " + str(cost_missing_shard_rp))

        print(
            str(OUTPUT["champions"]["owned"])
            + "/"
            + str(OUTPUT["champions"]["total"])
            + " champions owned"
        )
        print(
            str(OUTPUT["champions"]["owned"] + OUTPUT["champions"]["unique_shards"])
            + "/"
            + str(OUTPUT["champions"]["total"])
            + " shards/champions owned"
        )
        print("Missing " + str(get_be_needed()) + " BE to purchase all champions")

        conn.close()


if __name__ == "__main__":
    main()
