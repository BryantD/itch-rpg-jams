import argparse
import pprint
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

import click
import cloup
import dataset
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

REQ_HEADERS = {"user-agent": "itch-jam-bot/0.0.1"}


class GameType(Enum):
    UNCLASSIFIED = 0
    TABLETOP = 1
    TTRPG = 1
    DIGITAL = 2


@dataclass
class ItchJam:
    """Class for an individual itch game jam"""

    db_conn = None

    id: str
    name: str
    owner_name: str
    owner_id: str
    start: datetime
    duration: timedelta
    gametype: GameType = GameType.UNCLASSIFIED
    description: str = ""

    tabletop_keywords = [
        "tabletop",
        "osr",
        "fitd",
        "pbta",
        "physical game",
        "ttrpg",
        "sworddream",
        "srd",
        "system reference document",
    ]
    _itch_base_url = "https://itch.io"

    def __post_init__(self):
        if ItchJam.db_conn is None:
            try:
                ItchJam.db_conn = dataset.connect("sqlite:///itch_jams.sqlite")
            except Exception as e:
                print(f"ERROR: {e}")
        self.db_conn = ItchJam.db_conn

    def crawl(self):
        jam_url = f"{self._itch_base_url}/jam/{self.id}"
        try:
            req = requests.get(jam_url, headers=REQ_HEADERS)
        except requests.exceptions.RequestException as e:
            print(e)

        soup = BeautifulSoup(req.content.decode("utf-8"), "html.parser")
        self.description = str(soup.find("div", class_="jam_content"))
        return self.description

    def auto_classify(self):
        if any(
            element in self.description.lower() for element in self.tabletop_keywords
        ):
            self.gametype = GameType.TABLETOP

        return self.gametype

    def save(self):
        table = self.db_conn["itch_jams"]
        jam = dict(
            jam_id=self.id,
            jam_name=self.name,
            jam_owner_name=self.owner_name,
            jam_owner_id=self.owner_id,
            jam_start=self.start,
            jam_duration=self.duration,
            jam_gametype=self.gametype.value,
            jam_description=self.description,
        )
        table.upsert(jam, ["jam_id"])


class ItchJamList:
    def __init__(self, database="sqlite:///itch_jams.sqlite"):
        self._list = []
        self._database_name = database

    def __setitem__(self, jam_number, data):
        if type(data) == ItchJam:
            self._list[jam_number] = data
        else:
            raise TypeError("data must be a member of class ItchJam")

    def __getitem__(self, jam_number):
        return self._list[jam_number]

    #     def __iter__(self):
    #         self._current = 0
    #         return self
    #
    #     def __next__(self):
    #         self._current += 1
    #         if self._list[self._current]:
    #             return self._list[self._current]
    #         raise StopIteration

    def save(self):
        for jam in self.list:
            jam.save()

    def load(self, name=None, creator=None, gametype=None, id=None):
        db_conn = dataset.connect(self._database_name, row_type=dict)
        table = db_conn["itch_jams"]
        if name:
            jam_search = table.find(jam_name={""})
        elif creator:
            ...
        elif gametype:
            jam_search = table.find(jam_gametype=GameType[gametype.upper()].value)
        elif id:
            jam_search = table.find(jam_id=id)

        for jam in jam_search:
            self._list.append(
                ItchJam(
                    id=jam["jam_id"],
                    name=jam["jam_name"],
                    owner_name=jam["jam_owner_name"],
                    owner_id=jam["jam_owner_id"],
                    start=jam["jam_start"],
                    duration=jam["jam_duration"],
                    gametype=GameType(jam["jam_gametype"]).name,
                    description=jam["jam_description"],
                )
            )


def get_jam_list_page(page=1):
    base_url = "https://itch.io/jams/starting-this-month"
    jam_list = []

    req_payload = {"page": page}
    try:
        req = requests.get(base_url, headers=REQ_HEADERS, params=req_payload)
    except requests.exceptions.RequestException as e:
        print(e)

    soup = BeautifulSoup(req.content.decode("utf-8"), "html.parser")
    for jam in soup.find_all("div", class_="jam"):
        jam_id = jam.find("h3").find("a")["href"].split("/")[2]
        jam_name = jam.find("h3").find("a").get_text()

        jam_owner_name = jam.find("div", class_="hosted_by").find("a").get_text()
        jam_owner_url = jam.find("div", class_="hosted_by").find("a")["href"]
        # This is the most write-once way I could think of to extract a user ID
        # from a URL
        jam_owner_id = jam_owner_url[8:].split(".")[0]

        jam_start = jam.find("span", class_="date_countdown")["title"]
        jam_duration = jam.find("span", class_="date_duration").get_text()

        jam = ItchJam(
            name=jam_name,
            id=jam_id,
            owner_name=jam_owner_name,
            owner_id=jam_owner_id,
            start=jam_start,
            duration=jam_duration,
        )
        jam_list.append(jam)

    return jam_list


@cloup.group()
def cli():
    """Tool for generating lists of itch.io game jams"""


@cli.command()
@cloup.option("--force", is_flag=True)
@cloup.option("--url")
def crawl(force, url):
    """crawl upcoming game jams

    optionally force recrawls or crawl specific URLs
    """
    page = 1
    jam_list = []

    while new_jam_list := get_jam_list_page(page):
        jam_list.extend(new_jam_list)
        page = page + 1

    for jam in tqdm(jam_list):
        jam.crawl()
        jam.auto_classify()
        jam.save()


@cli.command()
@cloup.option_group(
    "Search options",
    cloup.option(
        "--type",
        type=cloup.Choice(["tabletop", "digital", "unclassified"]),
        default="tabletop",
    ),
    cloup.option("--name"),
    cloup.option("--creator"),
    cloup.option("--id"),
)
def list(type, name, creator, id):
    """list tabletop jams (optionally search for by type, name, creator, or id)"""

    jam_list = ItchJamList()
    # This needs fixing -- better to set a default if there are no options
    if type:
        jam_list.load(gametype=type)
    
    for jam in jam_list:
        print(f"{jam.name}")


@cli.command()
@cloup.argument("id", nargs=-1)
def show(id):
    """show detailed information for a jam"""

    db_conn = dataset.connect("sqlite:///itch_jams.sqlite", row_type=dict)
    table = db_conn["itch_jams"]
    for jam in table.find(jam_url={"=": GameType[type.upper()].value}):
        print(jam["jam_name"])


@cli.command()
@cloup.argument("id", nargs=-1)
@cloup.option(
    "--type",
    type=cloup.Choice(["tabletop", "digital", "unclassified"]),
)
def classify(id, type):
    """classify a jam as tabletop, digital, or unclassified"""
    print(f"classifying {id} as {type}")


@cli.command()
@cloup.argument("id", nargs=-1)
def delete(id):
    """delete a jam from the database"""
    print(f"Deleting {id}")
