import argparse
import pprint
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import re

import click
import cloup
import dataset
import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table
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

    id: str = None
    name: str = None
    owner_name: str = None
    owner_id: str = None
    start: datetime = None
    duration: int = None
    gametype: GameType = GameType.UNCLASSIFIED
    hashtag: str = None
    description: str = None

    tabletop_keywords = [
        "analog game",
        "analogue game",
        "belonging outside belonging",
        "fitd",
        "gmless",
        "megadungeon",
        "osr",
        "pamphlet",
        "pbta",
        "physical game",
        "srd",
        "sword dream",
        "sworddream",
        "system reference document",
        "tabletop",
        "ttrpg",
    ]
    _itch_base_url = "https://itch.io"

    def __post_init__(self):
        if ItchJam.db_conn is None:
            try:
                ItchJam.db_conn = dataset.connect("sqlite:///itch_jams.sqlite")
                ItchJam.table = self.db_conn["itch_jams"]
            except Exception as e:
                print(f"ERROR: {e}")
        self.db_conn = ItchJam.db_conn
        self.table = ItchJam.table

        if type(self.start) == str:
            self.start = datetime.fromisoformat(self.start)

        self.db = False

    def __str__(self):
        # Could stand to validate that the components exist
        
        soup = BeautifulSoup(self.description, "html.parser")
        description = re.sub("\n\n+", "\n\n", soup.get_text())
        jam_str = (
            f"Jam: {self.name} ({self.id})\n"
            f"Owner: {self.owner_name} ({self.owner_id})\n"
            f"URL: {self.url()}\n"
            f"Type: {GameType(self.gametype).name.lower()}\n"
            f"Hashtag: {self.hashtag}\n"
            f"Start: {self.start}\n"
            f"Duration: {self.duration} days\n"
            f"\n"
            f"{description}"
        )
        return jam_str

    def crawl(self, force_crawl=False):
        # Should be improved to crawl all missing data in the event this is called
        # outside of the ItchJamList crawl context

        saved_jam = self.table.find_one(jam_id=self.id)
        if force_crawl or (not saved_jam) or (not saved_jam["jam_description"]):
            jam_url = f"{self._itch_base_url}/jam/{self.id}"
            try:
                req = requests.get(jam_url, headers=REQ_HEADERS)
            except requests.exceptions.RequestException as e:
                print(e)
            http_code = req.status.code
            
            if req.ok:
                soup = BeautifulSoup(req.content.decode("utf-8"), "html.parser")

                self.description = str(soup.find("div", class_="jam_content"))
                hashtag_link = soup.find("div", class_="jam_host_header").find(
                    "a", href=re.compile("twitter\.com\/hashtag\/")
                )
                if hashtag_link:
                    self.hashtag = hashtag_link.get_text()
                
        else:
            self.description = saved_jam["jam_description"]

        return http_code

    def auto_classify(self):
        saved_jam = self.table.find_one(jam_id=self.id)
        if not saved_jam or saved_jam["jam_gametype"] == GameType.UNCLASSIFIED:
            if any(
                element in self.description.lower()
                for element in self.tabletop_keywords
            ):
                self.gametype = GameType.TABLETOP
        else:
            self.gametype = GameType(saved_jam["jam_gametype"])

        return self.gametype

    def save(self):
        jam = dict(
            jam_id=self.id,
            jam_name=self.name,
            jam_owner_name=self.owner_name,
            jam_owner_id=self.owner_id,
            jam_start=self.start,
            jam_duration=self.duration,
            jam_gametype=self.gametype.value,
            jam_hashtag=self.hashtag,
            jam_description=self.description,
        )
        self.table.upsert(jam, ["jam_id"])
        self.db = True

    def load(self, id):
        jam = self.table.find_one(jam_id=id)
        if jam:
            self.id = jam["jam_id"]
            self.name = jam["jam_name"]
            self.owner_name = jam["jam_owner_name"]
            self.owner_id = jam["jam_owner_id"]
            self.start = jam["jam_start"]
            self.duration = jam["jam_duration"]
            self.gametype = GameType(jam["jam_gametype"]).value
            self.hashtag = jam["jam_hashtag"]
            self.description = jam["jam_description"]
            self.db = True

        return self

    def delete(self):
        if self.db:
            self.table.delete(jam_id=self.id)

    def url(self):
        return f"{self._itch_base_url}/jam/{self.id}"

    def end(self):
        return self.start + timedelta(days=self.duration)


class ItchJamList:
    def __init__(self, database="sqlite:///itch_jams.sqlite"):
        self._list = []
        self._database_name = database

    def __setitem__(self, jam_number, data):
        if type(data) == ItchJam:
            self._list[jam_number] = data
        else:
            raise TypeError("item must be a member of class ItchJam")

    def __getitem__(self, jam_number):
        return self._list[jam_number]

    def __len__(self):
        return len(self._list)

    def append(self, data):
        if type(data) == ItchJam:
            self._list.append(data)
        else:
            raise TypeError("item must be a member of class ItchJam")

    def extend(self, data):
        if type(data) == list:
            for item in data:
                if type(data) != ItchJam:
                    raise TypeError("item must be a member of class ItchJam")
            self._list.extend(data)
        else:
            raise TypeError("data must be a list")

    def save(self):
        for jam in self.list:
            jam.save()

    def load(self, past_jams=False, name=None, owner=None, gametype=None, id=None):
        db_conn = dataset.connect(self._database_name)
        table = db_conn["itch_jams"]
        if name:
            jam_search = table.find(jam_name=name)
        elif owner:
            jam_search = table.find(jam_owner_id=owner)
        elif gametype:
            jam_search = table.find(jam_gametype=GameType[gametype.upper()].value)
        elif id:
            jam_search = table.find(jam_id=id)

        for jam in jam_search:
            if (
                jam["jam_start"] + timedelta(days=jam["jam_duration"]) > datetime.now()
                or past_jams
            ):
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

    def _crawl_page(self, page=1):
        base_url = "https://itch.io/jams/starting-this-month"
        req_payload = {"page": page}

        jams_flag = False

        try:
            req = requests.get(base_url, headers=REQ_HEADERS, params=req_payload)
        except requests.exceptions.RequestException as e:
            print(e)

        soup = BeautifulSoup(req.content.decode("utf-8"), "html.parser")
        for jam in soup.find_all("div", class_="jam"):
            jams_flag = True
            jam_id = jam.find("h3").find("a")["href"].split("/")[2]
            jam_name = jam.find("h3").find("a").get_text()

            jam_owner_name = jam.find("div", class_="hosted_by").find("a").get_text()
            jam_owner_url = jam.find("div", class_="hosted_by").find("a")["href"]
            # This is the most write-once way I could think of to extract a user ID
            # from a URL
            jam_owner_id = jam_owner_url[8:].split(".")[0]

            jam_start = jam.find("span", class_="date_countdown")["title"]
            jam_duration_string = jam.find("span", class_="date_duration").get_text()
            if "day" in jam_duration_string:
                jam_duration = int(jam_duration_string.split(" ")[0])
            elif "month" in jam_duration_string:
                jam_duration = int(jam_duration_string.split(" ")[0]) * 30
                # This is wrong, and could be replaced with something more sophisticated
                # that figures out ... whatever this means ... but I haven't seen any
                # jam durations measured in months so it's not so important
            elif "year" in jam_duration_string:
                jam_duration = int(jam_duration_string.split(" ")[0]) * 365

            jam = ItchJam(
                name=jam_name,
                id=jam_id,
                owner_name=jam_owner_name,
                owner_id=jam_owner_id,
                start=datetime.fromisoformat(jam_start),
                duration=jam_duration,
            )
            self._list.append(jam)
        return jams_flag

    def crawl(self, force_crawl=False):
        page = 1
        while self._crawl_page(page):
            page = page + 1

        for jam in tqdm(self._list):
            jam.crawl(force_crawl=force_crawl)
            jam.auto_classify()
            jam.save()


####    CLI functionality starts here


@cloup.group()
def cli():
    """Tool for generating lists of itch.io game jams"""


####    CLI argument: crawl


@cli.command()
@cloup.option("--force", is_flag=True, default=False)
@cloup.argument("id", nargs=-1)
def crawl(force, id):
    """crawl upcoming game jams

    optionally force recrawls or crawl specific URLs
    """
    if id:
        for i in id:
            jam = ItchJam(id=i)
            if jam.crawl():
                jam.save()
    else:
        jam_list = ItchJamList()
        jam_list.crawl(force_crawl=force)


####    CLI argument: list


@cli.command()
@cloup.option_group(
    "Search options",
    cloup.option(
        "--type",
        type=cloup.Choice(["tabletop", "digital", "unclassified"]),
    ),
    cloup.option("--name"),
    cloup.option("--owner"),
    cloup.option("--id"),
)
def list(type, name, owner, id):
    """list tabletop jams (optionally search for by type, name, owner, or id)"""

    jam_list = ItchJamList()

    if not (type or name or owner or id):
        type = "tabletop"

    if type:
        jam_list.load(gametype=type)
        query = f"Jam Type = {type}"
    elif name:
        jam_list.load(name=name)
        query = f"Jam Name = {name}"
    elif owner:
        jam_list.load(owner=owner)
        query = f"Jam Owner = {owner}"
    elif id:
        jam_list.load(id=id)
        query = f"Jam ID = {id}"

    if len(jam_list) > 0:
        console = Console()
        table = Table(title=f"{query}")

        table.add_column("Name")
        table.add_column("ID")
        table.add_column("URL", no_wrap=True)
        table.add_column("Owner")

        for jam in jam_list:
            table.add_row(jam.name, jam.id, jam.url(), jam.owner_name)

        console.print(table)


####    CLI argument: show


@cli.command()
@cloup.argument("id", nargs=-1)
def show(id):
    """show detailed information for a jam"""

    jam = ItchJam()
    jam.load(id=id)
    print(jam)


####    CLI argument: classify


@cli.command()
@cloup.argument("id", nargs=-1)
@cloup.option("--type", type=cloup.Choice(["tabletop", "digital", "unclassified"]))
def classify(id, type):
    """classify a jam as tabletop, digital, or unclassified"""

    if not id:
        id = []
        jam_list = ItchJamList()
        jam_list.load(gametype="unclassified")
        for jam in jam_list:
            id.append(jam.id)

    for i in id:
        jam = ItchJam()
        jam.load(id=i)
        if type:
            jam.gametype = GameType[type.upper()]
        else:
            print(jam)
            gametype = Prompt.ask(
                "Game type", choices=["tabletop", "digital", "unclassified"]
            )
            jam.gametype = GameType[gametype.upper()]
        print(f"Classifying {i} as {jam.gametype.name.lower()}")
        jam.save()


####    CLI argument: delete


@cli.command()
@cloup.argument("id", nargs=-1)
def delete(id):
    """delete a jam from the database"""

    for id in id:
        jam = ItchJam()
        jam.load(id=id)
        if jam.id:
            print(f"Deleting {id}")
            jam.delete()
        else:
            print(f"{id} not found")
