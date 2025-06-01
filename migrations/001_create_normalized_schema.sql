-- Migration 001: Create normalized schema
BEGIN TRANSACTION;

-- New jams table with explicit columns
CREATE TABLE itch_jams_new (
    jam_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    start_ts INTEGER NOT NULL,
    duration INTEGER NOT NULL,
    gametype INTEGER NOT NULL,
    hashtag TEXT,
    description TEXT
);

-- Table for jam owners (many-to-many relationship)
CREATE TABLE owners (
    owner_id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE jam_owners (
    jam_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    PRIMARY KEY (jam_id, owner_id),
    FOREIGN KEY (jam_id) REFERENCES itch_jams_new(jam_id) ON DELETE CASCADE,
    FOREIGN KEY (owner_id) REFERENCES owners(owner_id) ON DELETE CASCADE
);

-- Optional lookup table for gametype names
CREATE TABLE jam_gametypes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

INSERT INTO jam_gametypes (id, name) VALUES
    (0, 'unclassified'),
    (1, 'tabletop'),
    (2, 'digital');

COMMIT;