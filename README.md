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

```
itch-jam classify [OPTIONS] [ID]...

  classify a jam as tabletop, digital, or unclassified

Options:
  --type [tabletop|digital|unclassified]
  --help  Show this message and exit.
```

## crawl

```
Usage: itch-jam crawl [OPTIONS]

  crawl upcoming game jams

  optionally force recrawls or crawl specific URLs

Options:
  --force
  --url TEXT
  --help      Show this message and exit.
```

## delete

```
Usage: itch-jam delete [OPTIONS] [ID]...

  delete a jam from the database

Options:
  --help  Show this message and exit.
```

## list

```
Usage: itch-jam list [OPTIONS]

  list tabletop jams (optionally search for by type, name, creator, or id)

Search options:
  --type [tabletop|digital|unclassified]
  --name TEXT
  --creator TEXT
  --id TEXT

Other options:
  --help          Show this message and exit.
```

## show

```
Usage: itch-jam show [OPTIONS] [ID]...

  show detailed information for a jam

Options:
  --help  Show this message and exit.
```
