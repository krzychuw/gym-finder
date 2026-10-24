CREATE TABLE IF NOT EXISTS packages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    slug         TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_facilities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id      INTEGER NOT NULL REFERENCES packages(id),
    external_id     TEXT NOT NULL,
    name            TEXT NOT NULL,
    address_street  TEXT,
    address_city    TEXT,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    categories      TEXT,
    phone           TEXT,
    url             TEXT,
    raw_json        TEXT,
    scraped_at      TEXT NOT NULL,
    UNIQUE(package_id, external_id)
);

CREATE TABLE IF NOT EXISTS canonical_facilities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    address_street  TEXT,
    address_city    TEXT,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    categories      TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS facility_links (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_id     INTEGER NOT NULL REFERENCES canonical_facilities(id),
    raw_facility_id  INTEGER NOT NULL UNIQUE REFERENCES raw_facilities(id),
    match_score      REAL
);

CREATE INDEX IF NOT EXISTS idx_raw_facilities_package ON raw_facilities(package_id);
CREATE INDEX IF NOT EXISTS idx_facility_links_canonical ON facility_links(canonical_id);
