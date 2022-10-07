from datetime import datetime, timedelta
from enum import Enum
import json
import sqlite3
import re

import cloup

import html2text
import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, TextColumn
from rich.prompt import Prompt
from rich.table import Table

REQ_HEADERS = {"user-agent": "itch-jam-bot/0.9.0"}


class GameType(Enum):
    UNCLASSIFIED = 0
    TABLETOP = 1
    TTRPG = 1
    DIGITAL = 2


class ItchJam:
    """Class for an individual itch game jam"""

    db_conn = None

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

    def __init__(
        self,
        id=None,
        name=None,
        owners={},
        start=None,
        duration=None,
        gametype=GameType.UNCLASSIFIED,
        hashtag=None,
        description=None,
        crawled=False,
    ):
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
                ItchJam.db_conn = sqlite3.connect("itch_jam.db")
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

        jam_str = (
            f"Jam: {self.name} ({self.id})\n"
            f"Owner(s): {self.owner_ids()}\n"
            f"URL: {self.url()}\n"
            f"Type: {GameType(self.gametype).name.lower()}\n"
            f"Hashtag: {self.hashtag}\n"
            f"Start: {self.start}\n"
            f"Duration: {self.duration} days\n"
            f"\n"
            f"{description}"
        )
        return jam_str

    def owner_ids(self):
        if self.owners:
            return ", ".join(self.owners.keys())
        else:
            return ""

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

            owners = {}
            for a_tag in soup.find("div", class_="jam_host_header").find_all(
                "a", href=re.compile("\.itch\.io$")
            ):
                owner_name = a_tag.get_text()
                owner_id = a_tag["href"][8:-8]  # slurped out of the center of the URL
                owners[owner_id] = owner_name
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
            WHERE jam_id = :jam_id
            """,
            {"jam_id": self.id},
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
            {"jam_id": id},
        ).fetchone()

        if saved_jam:
            jam_data = json.loads(saved_jam[1])
            self.id = saved_jam[0]
            self.name = jam_data["jam_name"]
            self.owners = jam_data["jam_owners"]
            self.start = datetime.utcfromtimestamp(jam_data["jam_start"])
            self.duration = jam_data["jam_duration"]
            self.gametype = GameType(jam_data["jam_gametype"]).value
            self.hashtag = jam_data["jam_hashtag"]
            self.description = jam_data["jam_description"]
            self.crawled = True

        return self

    def delete(self):
        if self.crawled:
            self.db_conn.execute(
                """
                DELETE FROM itch_jams WHERE jam_id = :jam_id
                """,
                {"jam_id": self.id},
            )
            self.db_conn.commit()
            self.crawled = False

    def url(self):
        return f"{self._itch_base_url}/jam/{self.id}"

    def end(self):
        return self.start + timedelta(days=self.duration)


class ItchJamList:

    db_conn = None

    def __init__(self):
        self._list = []

        if ItchJamList.db_conn is None:
            try:
                ItchJamList.db_conn = sqlite3.connect("itch_jam.db")
            except Exception as e:
                print(f"ERROR: {e}")

        self.db_conn = ItchJamList.db_conn

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

    def load(self, past_jams=False, owner_id=None, gametype=None, jam_id=None):
        if owner_id:
            jam_search = self.db_conn.execute(
                """
                SELECT itch_jams.jam_id, itch_jams.jam_data
                FROM itch_jams, json_tree(itch_jams.jam_data, "$.jam_owners")
                WHERE json_tree.key = :owner_id
                """,
                {"owner_id": owner_id},
            )
        elif gametype:
            jam_search = self.db_conn.execute(
                """
                SELECT itch_jams.jam_id, itch_jams.jam_data
                FROM itch_jams, json_each(itch_jams.jam_data, "$.jam_gametype")
                WHERE json_each.value = :gametype
                """,
                {"gametype": GameType[gametype.upper()].value},
            )
        elif id:
            jam_search = self.db_conn.execute(
                """
                SELECT itch_jams.jam_id, itch_jams.jam_data
                FROM itch_jams WHERE jam_id = :jam_id
                """,
                {"jam_id": jam_id},
            )

        for jam in jam_search:
            jam_json = json.loads(jam[1])
            if (
                datetime.utcfromtimestamp(jam_json["jam_start"])
                + timedelta(days=jam_json["jam_duration"])
                > datetime.now()
                or past_jams
            ):
                jam_load = ItchJam()
                jam_load.load(id=jam[0])
                self._list.append(jam_load)

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

        cur = self.db_conn.cursor()
        cur.execute(
            """
            SELECT jam_id FROM itch_jams
            """
        )
        jam_ids = [item[0] for item in cur.fetchall()]
        cur.close()

        while self._crawl_page(page):
            page = page + 1

        with Progress(
            *Progress.get_default_columns(), TextColumn("[bold]{task.fields[jam_name]}")
        ) as progress:
            crawl_task = progress.add_task(
                "Crawling...", total=len(self._list), jam_name=""
            )
            for jam in self._list:
                if force_crawl or not jam.id in jam_ids:
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
@cloup.argument("id", nargs=-1, help="One or more jam IDs to crawl")
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
    cloup.option("--owner"),
    cloup.option("--id"),
)
@cloup.option("--old", is_flag=True, default=False, help="Include old jams")
def list(type, owner, id, old):
    """list tabletop jams (optionally search by type, owner ID, or jam ID)"""

    jam_list = ItchJamList()

    if not (type or owner or id):
        type = "tabletop"

    if type:
        jam_list.load(gametype=type, past_jams=old)
        query = f"Jam Type = {type}"
    elif id:
        jam_list.load(jam_id=id, past_jams=old)
        query = f"Jam ID = {id}"
    elif owner:
        jam_list.load(owner_id=owner, past_jams=old)
        query = f"Jam Owner = {owner}"

    if len(jam_list) > 0:
        console = Console()
        table = Table(title=f"{query}")

        table.add_column("Name")
        table.add_column("ID")
        table.add_column("URL", no_wrap=True)
        table.add_column("Owner(s)")

        for jam in jam_list:
            table.add_row(jam.name, jam.id, jam.url(), jam.owner_ids())

        console.print(table)


####    CLI argument: show


@cli.command()
@cloup.argument("id", nargs=-1, help="One or more jam IDs to show")
def show(id):
    """show detailed information for jams"""

    for i in id:
        jam = ItchJam()
        jam.load(id=i)
        if jam.crawled:
            print(jam)


####    CLI argument: classify


@cli.command()
@cloup.argument("id", nargs=-1, help="One or more jam IDs to classify")
@cloup.option("--type", type=cloup.Choice(["tabletop", "digital", "unclassified"]))
def classify(id, type):
    """classify jams as tabletop, digital, or unclassified"""

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
@cloup.argument("id", nargs=-1, help="One or more jam IDs to delete")
def delete(id):
    """delete jams from the database"""

    for id in id:
        jam = ItchJam()
        jam.load(id=id)
        if jam.crawled:
            print(f"Deleting {id}")
            jam.delete()
        else:
            print(f"{id} not found")
