import cloup
import deepl
from click_extra import config_option
from datetime import datetime, timedelta
from jinja2 import Environment, FileSystemLoader, select_autoescape
from lingua import Language, LanguageDetectorBuilder
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
from math import ceil

from itch_jam_lib import GameType, ItchJam, ItchJamList


@cloup.group()
@cloup.option("--deepl-api-key")
@config_option(default="./itch_jam.toml")
@cloup.pass_context
def itch_jam(ctx, deepl_api_key):
    """Tool for generating lists of itch.io game jams"""

    ctx.ensure_object(dict)
    translator = deepl.Translator(deepl_api_key)
    ctx.obj["translator"] = translator

    languages = [
        Language.SPANISH,
        Language.PORTUGUESE,
        Language.CATALAN,
        Language.TAGALOG,
        Language.ENGLISH,
        Language.ALBANIAN,
        Language.ITALIAN,
        Language.FRENCH,
        Language.ROMANIAN,
        Language.SLOVAK,
        Language.CZECH,
        Language.DUTCH,
        Language.CROATIAN,
        Language.HUNGARIAN,
        Language.AFRIKAANS,
        Language.ARABIC,
        Language.ARMENIAN,
        Language.BENGALI,
        Language.BOSNIAN,
        Language.BULGARIAN,
        Language.CHINESE,
        Language.DANISH,
        Language.ESTONIAN,
        Language.FINNISH,
        Language.GERMAN,
        Language.GREEK,
        Language.HEBREW,
        Language.HINDI,
        Language.ICELANDIC,
        Language.INDONESIAN,
        Language.JAPANESE,
        Language.KOREAN,
        Language.LATVIAN,
        Language.LITHUANIAN,
        Language.PERSIAN,
        Language.POLISH,
        Language.PUNJABI,
        Language.RUSSIAN,
        Language.SERBIAN,
        Language.SLOVENE,
        Language.SWEDISH,
        Language.TAMIL,
        Language.THAI,
        Language.TURKISH,
        Language.UKRAINIAN,
        Language.VIETNAMESE,
    ]
    detector = LanguageDetectorBuilder.from_languages(*languages).build()
    ctx.obj["detector"] = detector


@itch_jam.command()
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


@itch_jam.command()
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
@cloup.option("--all", is_flag=True, default=False, help="Include all jams")
@cloup.option("--html", is_flag=True, default=False, help="HTML output")
@cloup.argument("templates", type=cloup.Path(), nargs=-1)
def list(templates, type, owner, id, old, all, html):
    """list tabletop jams (optionally search by type, owner ID, or jam ID)"""

    jam_list = ItchJamList()

    if not (type or owner or id):
        type = "tabletop"

    if old:
        old = True
        new = False
    elif all:
        old = True
        new = True
    else:
        new = True

    if type:
        jam_list.load(gametype=type, past_jams=old, current_jams=new)
        query = f"Jam Type = {type}"
    elif id:
        jam_list.load(jam_id=id, past_jams=old, current_jams=new)
        query = f"Jam ID = {id}"
    elif owner:
        jam_list.load(owner_id=owner, past_jams=old, current_jams=new)
        query = f"Jam Owner = {owner}"

    if len(jam_list) > 0:
        jam_list.sort()
        if html:
            if not templates:
                templates = "./templates"
            env = Environment(
                loader=FileSystemLoader(templates), autoescape=select_autoescape()
            )
            # split lists into current and finished
            [jam_list_current, jam_list_finished] = [[], []]
            for jam in jam_list:
                if jam.start + timedelta(days=jam.duration) > datetime.now():
                    jam_list_current.append(jam)
                else:
                    jam_list_finished.append(jam)
            if new:
                template = env.get_template("index.html.jinja")
                rendered_template = template.render(
                    jams=jam_list_current, date=datetime.now()
                )
                with open("output/index.html", "w") as static_file:
                    static_file.write(rendered_template)
            if old:
                items_per_page = 50  # TODO: make this configurable

                pages = ceil(len(jam_list_finished) / items_per_page)

                for page in range(1, pages + 1):
                    start = (page - 1) * items_per_page
                    end = start + items_per_page
                    page_data = jam_list_finished[start:end]

                    # Render the template for this page
                    template = env.get_template("index-finished.html.jinja")

                    rendered_template = template.render(
                        jams=page_data,
                        current_page=page,
                        pages=pages,
                        date=datetime.now(),
                    )

                    # Save the rendered template to a file
                    with open(f"output/index-finished-{page}.html", "w") as static_file:
                        static_file.write(rendered_template)
        else:
            console = Console()
            table = Table(title=f"{query}")

            table.add_column("Name")
            table.add_column("ID")
            table.add_column("URL", no_wrap=True)
            table.add_column("Owner(s)")

            for jam in jam_list:
                table.add_row(jam.name, jam.id, jam.url(), jam.owner_ids())

            console.print(table)


@itch_jam.command()
@cloup.argument("id", nargs=-1, help="One or more jam IDs to show")
@cloup.pass_context
def show(ctx, id):
    """show detailed information for jams"""

    for i in id:
        jam = ItchJam(id=i, ctx=ctx)
        if jam.crawled:
            print(jam)


@itch_jam.command()
@cloup.argument("id", nargs=-1, help="One or more jam IDs to classify")
@cloup.option("--type", type=cloup.Choice(["tabletop", "digital", "unclassified"]))
@cloup.pass_context
def classify(ctx, id, type):
    """classify jams as tabletop, digital, or unclassified"""

    if not id:
        id = []
        jam_list = ItchJamList()
        jam_list.load(gametype="unclassified")
        for jam in jam_list:
            id.append(jam.id)

    for i in id:
        jam = ItchJam(ctx=ctx)
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


@itch_jam.command()
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

if __name__ == "__main__":
    itch_jam()

