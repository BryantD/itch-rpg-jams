# Classes and helpers for interacting with itch.io game jams

import re
import sqlite3
import tomllib
from datetime import datetime, timedelta
from enum import Enum

import html2text
import requests
from bs4 import BeautifulSoup
from rich.progress import Progress, TextColumn

REQ_HEADERS = {"user-agent": "itch-jam-bot/0.9.0"}


class GameType(Enum):
    UNCLASSIFIED = 0
    TABLETOP = 1
    TTRPG = 1
    DIGITAL = 2


class ItchJam:
    """Class for an individual itch game jam"""

    db_conn = None

    _itch_base_url = "https://itch.io"

    def __init__(
        self,
        ctx=None,
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
        self.ctx = ctx
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

        if not self.name:
            self.load(id=self.id)

        if self.start is str:
            self.start = datetime.fromisoformat(f"{self.start}+00:00")

    def __str__(self):
        # Could stand to validate that the components exist

        h2t = html2text.HTML2Text()
        h2t.ignore_links = True
        h2t.ignore_images = True
        h2t.strong_mark = "*"

        language_detect = self.ctx.obj["detector"].detect_language_of(self.description)
        if language_detect.name != "ENGLISH":
            print(f"Translating from {language_detect.name}")
            desc = str(
                self.ctx.obj["translator"].translate_text(
                    self.description, target_lang="EN-US"
                )
            )
        else:
            desc = self.description

        description = re.sub(r"(\n\s*)+\n+", "\n\n", h2t.handle(desc))

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
                "a", href=re.compile(r"\.itch\.io$")
            ):
                owner_name = a_tag.get_text()
                owner_id = a_tag["href"][8:-8]
                owners[owner_id] = owner_name
            self.owners = owners

            hashtag_link = soup.find("div", class_="jam_host_header").find(
                "a", href=re.compile(r"twitter\.com\/hashtag\/")
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
        with open("keywords.toml", "rb") as f:
            keywords = tomllib.load(f)

        row = self.db_conn.execute(
            "SELECT gametype FROM itch_jams WHERE jam_id = ?", (self.id,)
        ).fetchone()
        if row and row[0] is not None:
            self.gametype = GameType(row[0])
            return self.gametype

        desc_lower = (self.description or "").lower()
        name_lower = (self.name or "").lower()
        if any(word in desc_lower for word in keywords.get("tabletop_keywords", [])):
            self.gametype = GameType.TABLETOP
        elif any(
            word in desc_lower for word in keywords.get("digital_keywords", [])
        ) or any(word in name_lower for word in keywords.get("digital_keywords", [])):
            self.gametype = GameType.DIGITAL
        else:
            self.gametype = GameType.UNCLASSIFIED

        return self.gametype

    def save(self):
        cur = self.db_conn.cursor()
        cur.execute(
            """
            INSERT INTO itch_jams (
                jam_id, name, start_ts, duration, gametype, hashtag, description
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(jam_id) DO UPDATE SET
              name=excluded.name,
              start_ts=excluded.start_ts,
              duration=excluded.duration,
              gametype=excluded.gametype,
              hashtag=excluded.hashtag,
              description=excluded.description
            """,
            (
                self.id,
                self.name,
                int(self.start.timestamp()),
                self.duration,
                self.gametype.value
                if isinstance(self.gametype, GameType)
                else self.gametype,
                self.hashtag,
                self.description,
            ),
        )
        cur.execute("DELETE FROM jam_owners WHERE jam_id = ?", (self.id,))
        for owner_id, owner_name in (self.owners or {}).items():
            cur.execute(
                "INSERT OR IGNORE INTO owners (owner_id, name) VALUES (?, ?)",
                (owner_id, owner_name),
            )
            cur.execute(
                "INSERT INTO jam_owners (jam_id, owner_id) VALUES (?, ?)",
                (self.id, owner_id),
            )
        self.db_conn.commit()
        self.crawled = True

    def load(self, id):
        row = self.db_conn.execute(
            """
            SELECT jam_id, name, start_ts, duration, gametype, hashtag, description
              FROM itch_jams WHERE jam_id = ?
            """,
            (id,),
        ).fetchone()
        if row:
            (
                self.id,
                self.name,
                start_ts,
                self.duration,
                gametype_val,
                self.hashtag,
                self.description,
            ) = row
            self.start = datetime.utcfromtimestamp(start_ts)
            self.gametype = gametype_val
            owners_rows = self.db_conn.execute(
                """
                SELECT o.owner_id, o.name
                  FROM owners o
                  JOIN jam_owners jo ON o.owner_id = jo.owner_id
                 WHERE jo.jam_id = ?
                """,
                (self.id,),
            ).fetchall()
            self.owners = {owner_id: name for owner_id, name in owners_rows}
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
        if isinstance(data, ItchJam):
            self._list[jam_number] = data
        else:
            raise TypeError("item must be a member of class ItchJam")

    def __getitem__(self, jam_number):
        return self._list[jam_number]

    def __len__(self):
        return len(self._list)

    def append(self, data):
        if isinstance(data, ItchJam):
            self._list.append(data)
        else:
            raise TypeError("item must be a member of class ItchJam")

    def extend(self, data):
        if data is list:
            for item in data:
                if not isinstance(data, ItchJam):
                    raise TypeError("item must be a member of class ItchJam")
            self._list.extend(data)
        else:
            raise TypeError("data must be a list")

    def sort(self):
        self._list.sort(key=lambda jam: jam.end())

    def save(self):
        for jam in self.list:
            jam.save()

    def load(
        self,
        past_jams=False,
        current_jams=True,
        owner_id=None,
        gametype=None,
        jam_id=None,
    ):
        if owner_id:
            jam_search = self.db_conn.execute(
                "SELECT jam_id FROM jam_owners WHERE owner_id = ?", (owner_id,)
            )
        elif gametype:
            gt_val = GameType[gametype.upper()].value
            jam_search = self.db_conn.execute(
                "SELECT jam_id FROM itch_jams WHERE gametype = ?", (gt_val,)
            )
        elif jam_id:
            jam_search = self.db_conn.execute(
                "SELECT jam_id FROM itch_jams WHERE jam_id = ?", (jam_id,)
            )
        else:
            jam_search = self.db_conn.execute("SELECT jam_id FROM itch_jams")

        for (jid,) in jam_search:
            jam = ItchJam(id=jid)
            end_dt = jam.end()
            now = datetime.now()
            if (current_jams and end_dt > now) or (past_jams and end_dt < now):
                self._list.append(jam)

    def _crawl_page(self, page=1, list="upcoming"):
        if list == "upcoming":
            base_url = "https://itch.io/jams/upcoming"
        elif list == "in-progress":
            base_url = "https://itch.io/jams/in-progress"
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

        page = 1
        while self._crawl_page(page, list="in-progress"):
            page = page + 1

        page = 1
        while self._crawl_page(page, list="upcoming"):
            page = page + 1

        with Progress(
            *Progress.get_default_columns(), TextColumn("[bold]{task.fields[jam_name]}")
        ) as progress:
            crawl_task = progress.add_task(
                "Crawling...", total=len(self._list), jam_name=""
            )
            for jam in self._list:
                if force_crawl or jam.id not in jam_ids:
                    jam.crawl()
                    jam.auto_classify()
                    match jam.gametype:
                        case GameType.UNCLASSIFIED:
                            emoji = ""
                        case GameType.TABLETOP:
                            emoji = ":game_die: "
                        case GameType.DIGITAL:
                            emoji = ":joystick: "
                    progress.console.print(
                        f"{emoji}{jam.name} <{jam.url()}>: {jam.gametype.name.lower()}"
                    )
                    jam.save()
                progress.update(crawl_task, advance=1, jam_name=jam.name)
