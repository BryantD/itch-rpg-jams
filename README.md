# Intro

I wrote this cause I wanted it! I am maintaining an instance of the resulting list at https://physicalgamejams.com/.

# Installation

1. Pull down the git repo
2. `pip install .`
3. `sqlite3 itch_jam.db < itch_jam.sql`

# Usage

```
itch-jam [OPTIONS] COMMAND [ARGS]...

  Tool for generating lists of itch.io game jams

Options:
  --help  Show this message and exit.

Commands:
  classify  classify a jam as tabletop, digital, or unclassified
  crawl     crawl upcoming game jams
  delete    delete a jam from the database
  list      list tabletop jams (optionally search for by type, name,...
  show      show detailed information for a jam
```

## classify

If you don't specify a type, classification will be interactive. If you don't specify a jam, all unclassified jams will be presented for classification in order.

```
itch-jam classify [OPTIONS] [ID]...

  classify jams as tabletop, digital, or unclassified

Positional arguments:
  [ID]...  One or more jam IDs to classify

Options:
  --type [tabletop|digital|unclassified]
  --help  Show this message and exit.
```

## crawl

If you don't specify a jam to crawl, the upcoming jams page will be crawled.

While crawling, a good faith effort to identify tabletop games is made based on keywords. The keywords currently used are towards the top of the code in the ItchJam class.

```
Usage: itch-jam crawl [OPTIONS] [ID]...

  crawl upcoming game jams

  optionally force recrawls or crawl specific IDs

Positional arguments:
  [ID]...  One or more jam IDs to crawl

Options:
  --force
  --help   Show this message and exit.
```

## delete

```
Usage: itch-jam delete [OPTIONS] [ID]...

  delete jams from the database

Positional arguments:
  [ID]...  One or more jam IDs to delete

Options:
  --help  Show this message and exit.
```

## list

By default, this lists tabletop jams.

```
Usage: itch-jam list [OPTIONS]

  list tabletop jams (optionally search by type, owner ID, or jam ID)

Search options:
  --type [tabletop|digital|unclassified]
  --owner TEXT
  --id TEXT

Other options:
  --old         Include old jams
  --html        HTML output
  --help        Show this message and exit.
```

## show

```
Usage: itch-jam show [OPTIONS] [ID]...

  show detailed information for jams

Positional arguments:
  [ID]...  One or more jam IDs to show

Options:
  --help  Show this message and exit.
```
