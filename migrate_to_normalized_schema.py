#!/usr/bin/env python3
"""
Script to migrate the existing itch_jam.db from a JSON-blob schema
to a normalized schema with explicit tables and columns.
"""
import json
import os
import shutil
import sqlite3
import sys

DB_FILE = "itch_jam.db"
BACKUP_FILE = DB_FILE + ".bak"
MIGRATION_SQL = os.path.join("migrations", "001_create_normalized_schema.sql")


def main():
    # Step 3a: backup existing database
    if not os.path.exists(DB_FILE):
        print(f"Database file '{DB_FILE}' not found.")
        sys.exit(1)
    if os.path.exists(BACKUP_FILE):
        print(f"Backup already exists at '{BACKUP_FILE}'. Remove it before migrating.")
        sys.exit(1)
    shutil.copy2(DB_FILE, BACKUP_FILE)
    print(f"Backup created: {BACKUP_FILE}")

    # Open connection and enable foreign keys
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    # Step 3b: create new tables
    if not os.path.exists(MIGRATION_SQL):
        print(f"Migration SQL file not found: {MIGRATION_SQL}")
        conn.close()
        sys.exit(1)
    with open(MIGRATION_SQL, "r") as f:
        migration_sql = f.read()
    cur.executescript(migration_sql)
    print("Created new normalized schema tables.")

    # Step 3c: migrate data from old JSON blob
    cur.execute("SELECT jam_id, jam_data FROM itch_jams;")
    rows = cur.fetchall()
    print(f"Found {len(rows)} jams to migrate.")
    for jam_id, jam_data in rows:
        data = json.loads(jam_data)
        # Insert into itch_jams_new
        cur.execute(
            """INSERT INTO itch_jams_new (
                jam_id, name, start_ts, duration, gametype, hashtag, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?);""",
            (
                jam_id,
                data.get("jam_name"),
                int(data.get("jam_start", 0)),
                data.get("jam_duration"),
                data.get("jam_gametype"),
                data.get("jam_hashtag"),
                data.get("jam_description"),
            ),
        )
        # Insert owners and join entries
        owners = data.get("jam_owners", {}) or {}
        for owner_id, owner_name in owners.items():
            cur.execute(
                "INSERT OR IGNORE INTO owners (owner_id, name) VALUES (?, ?);",
                (owner_id, owner_name),
            )
            cur.execute(
                "INSERT INTO jam_owners (jam_id, owner_id) VALUES (?, ?);",
                (jam_id, owner_id),
            )
    conn.commit()
    print("Data migration to normalized tables complete.")

    # Step 3d: validation
    cur.execute("SELECT COUNT(*) FROM itch_jams;")
    old_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM itch_jams_new;")
    new_count = cur.fetchone()[0]
    print(f"Original itch_jams rows: {old_count}")
    print(f"New itch_jams_new rows: {new_count}")

    cur.close()
    conn.close()
    print("Migration finished. Review counts and, if happy, consider renaming tables.")


if __name__ == "__main__":
    main()
