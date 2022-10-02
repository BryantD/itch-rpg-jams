import argparse
import pprint
from datetime import datetime, timedelta
from enum import Enum
import json
import sqlite3
import re

import click
import cloup

# import dataset
import html2text
import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, TextColumn
from rich.prompt import Prompt
from rich.table import Table

REQ_HEADERS = {"user-agent": "itch-jam-bot/0.0.1"}


class GameType(Enum):
    UNCLASSIFIED = 0
    TABLETOP = 1
    TTRPG = 1
    DIGITAL = 2


class ItchJam:
    """Class for an individual itch game jam"""

    db_conn = None
    table = None

    _tabletop_keywords = [
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

    def __init__(self, id=None, name=None, owners=[], start=None, duration=None, gametype=GameType.UNCLASSIFIED, hashtag=None, description=None, crawled=False):  
        self.id = id
        self.name = name
        self.owners = owners
        self.start = start
        self.duration = duration
        self.gametype = gametype
        self.hashtag = hashtag
        self.description = description
        self.crawled = crawled

        if ItchJam.db_conn is None:
            try:
                ItchJam.db_conn = sqlite3.connect("test.db")
            except Exception as e:
                print(f"ERROR: {e}")

        self.db_conn = ItchJam.db_conn

        if type(self.start) == str:
            self.start = datetime.fromisoformat(f"{self.start}+00:00")

    def __str__(self):
        # Could stand to validate that the components exist

        h2t = html2text.HTML2Text()
        h2t.ignore_links = True
        h2t.ignore_images = True
        h2t.strong_mark = "*"
        description = re.sub("(\n\s*)+\n+", "\n\n", h2t.handle(self.description))
        owner_string = ", ".join(map(lambda tup: tup[0], self.owners))
        
        jam_str = (
            f"Jam: {self.name} ({self.id})\n"
            f"Owner(s): {owner_string}\n"
            f"URL: {self.url()}\n"
            f"Type: {GameType(self.gametype).name.lower()}\n"
            f"Hashtag: {self.hashtag}\n"
            f"Start: {self.start}\n"
            f"Duration: {self.duration} days\n"
            f"\n"
            f"{description}"
        )
        return jam_str

    def crawl(self):
        jam_url = f"{self._itch_base_url}/jam/{self.id}"
        try:
            req = requests.get(jam_url, headers=REQ_HEADERS)
        except requests.exceptions.RequestException as e:
            print(e)

        if req.ok:
            self.crawled = True
            soup = BeautifulSoup(req.content.decode("utf-8"), "html.parser")

            self.name = soup.find("h1", class_="jam_title_header").get_text()
            self.description = str(soup.find("div", class_="jam_content"))

            owners = []
            for a_tag in soup.find("div", class_="jam_host_header").find_all(
                "a", href=re.compile("\.itch\.io$")
            ):
                owner_name = a_tag.get_text()
                owner_id = a_tag["href"][8:-8] # slurped out of the center of the URL
                owners.append((owner_id, owner_name))
            self.owners = owners

            hashtag_link = soup.find("div", class_="jam_host_header").find(
                "a", href=re.compile("twitter\.com\/hashtag\/")
            )
            if hashtag_link:
                self.hashtag = hashtag_link.get_text()

            date_spans = soup.find_all("span", class_="date_format")
            self.start = datetime.fromisoformat(f"{date_spans[0].get_text()}+00:00")
            end_date = datetime.fromisoformat(f"{date_spans[1].get_text()}+00:00")
            duration = end_date - self.start
            self.duration = duration.days

        return self.crawled

    def auto_classify(self):
        saved_jam_gametype = self.db_conn.execute(
            """
            SELECT json_each.value 
                FROM itch_jams, json_each(itch_jams.jam_data, '$.jam_gametype')
            """
        ).fetchone()
        if saved_jam_gametype:
            self.gametype = GameType(saved_jam_gametype[0])
        elif any(
            element in self.description.lower() for element in self._tabletop_keywords
        ):
            self.gametype = GameType.TABLETOP

        return self.gametype

    def save(self):
        cur = self.db_conn.cursor()
        jam = dict(
            jam_name=self.name,
            jam_owners=self.owners,
            jam_start=self.start.timestamp(),
            jam_duration=self.duration,
            jam_gametype=self.gametype.value,
            jam_hashtag=self.hashtag,
            jam_description=self.description,
        )
        cur.execute(
            """
            INSERT INTO itch_jams VALUES (:jam_id, :jam_data) ON CONFLICT(jam_id) 
                DO UPDATE SET jam_data=:jam_data
            """,
            {"jam_id": self.id, "jam_data": json.dumps(jam)},
        )
        cur.close()
        self.db_conn.commit()

        self.crawled = True

    def load(self, id):
        saved_jam = self.db_conn.execute(
            """
            SELECT jam_id, jam_data FROM itch_jams WHERE jam_id = :jam_id
            """,
            {"jam_id": id}
        ).fetchone()
        
        if saved_jam:
            jam_data = json.loads(saved_jam[1])
            self.id = saved_jam[0]
            self.name = jam_data["jam_name"]
            self.owners = jam_data["jam_owners"]
            # Fix this
            self.start = jam_data["jam_start"]
            self.duration = jam_data["jam_duration"]
            self.gametype = GameType(jam_data["jam_gametype"]).value
            self.hashtag = jam_data["jam_hashtag"]
            self.description = jam_data["jam_description"]
            self.crawled = True

        return self


        # select itch_jams.jam_id from itch_jams, json_each(itch_jams.jam_data, '$.jam_duration') where json_each.value == 11;
        # select itch_jams.jam_id from itch_jams, json_tree(itch_jams.jam_data, '$.jam_owner') where json_tree.key == "testid";
        # datetime.utcfromtimestamp(timestamp)

    def delete(self):
        if self.crawled:
            self.table.delete(jam_id=self.id)
            self.crawled = False

    def url(self):
        return f"{self._itch_base_url}/jam/{self.id}"

    def end(self):
        return self.start + timedelta(days=self.duration)


class ItchJamList:

    db_conn = None
    table = None

    def __init__(self, database="sqlite:///itch_jams.sqlite"):
        self._list = []
        self._database_name = database

        if ItchJamList.db_conn is None:
            try:
                ItchJamList.db_conn = dataset.connect("sqlite:///itch_jams.sqlite")
            except Exception as e:
                print(f"ERROR: {e}")

        if ItchJamList.table is None:
            ItchJamList.table = self.db_conn["itch_jams"]

        self.db_conn = ItchJamList.db_conn
        self.table = ItchJamList.table

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

    def load(self, past_jams=False, name=None, gametype=None, id=None):
        if name:
            jam_search = self.table.find(jam_name=name)
        elif gametype:
            jam_search = self.table.find(jam_gametype=GameType[gametype.upper()].value)
        elif id:
            jam_search = self.table.find(jam_id=id)

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

            jam = ItchJam(id=jam_id)
            self._list.append(jam)
        return jams_flag

    def crawl(self, force_crawl=False):
        page = 1

        while self._crawl_page(page):
            page = page + 1

        with Progress(
            *Progress.get_default_columns(), TextColumn("[bold]{task.fields[jam_name]}")
        ) as progress:
            crawl_task = progress.add_task(
                "Crawling...", total=len(self._list), jam_name=""
            )
            for jam in self._list:
                if force_crawl or not self.table.find_one(jam_id=jam.id):
                    jam.crawl()
                    jam.auto_classify()
                    jam.save()
                progress.update(crawl_task, advance=1, jam_name=jam.name)


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
                jam.auto_classify()
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
    elif id:
        jam_list.load(id=id)
        query = f"Jam ID = {id}"

    if len(jam_list) > 0:
        console = Console()
        table = Table(title=f"{query}")

        table.add_column("Name")
        table.add_column("ID")
        table.add_column("URL", no_wrap=True)
        table.add_column("Owner(s)")

        for jam in jam_list:
            table.add_row(jam.name, jam.id, jam.url(), jam.owner_name)

        console.print(table)


####    CLI argument: show


@cli.command()
@cloup.argument("id", nargs=-1)
def show(id):
    """show detailed information for a jam"""

    for i in id:
        jam = ItchJam()
        jam.load(id=i)
        if jam.crawled:
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
        if jam.crawled:
            print(f"Deleting {id}")
            jam.delete()
        else:
            print(f"{id} not found")
