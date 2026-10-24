"""Scrapes the public BeActive club list nationwide and stores all facilities
into raw_facilities.

The our-clubs page (ebeactive.pl/en/our-clubs) server-renders the full
nationwide club list as a `const clubs = [...]` JSON array embedded in the
page (no separate API endpoint, no bot-detection) - so we just fetch that one
page, no per-city filtering needed.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.categories import normalize_category
from db import get_connection, init_db

CLUBS_URL = "https://ebeactive.pl/en/our-clubs"
PACKAGE_SLUG = "beactive"


def fetch_all_clubs() -> list[dict]:
    resp = httpx.get(CLUBS_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    match = re.search(r"const clubs = (\[.*?\]);", resp.text, re.DOTALL)
    if not match:
        raise RuntimeError("Could not find embedded `const clubs = [...]` data on the page")
    return json.loads(match.group(1))


def to_row(item: dict) -> dict:
    categories = [
        normalize_category(part)
        for part in (item.get("description") or "").split(",")
        if part.strip()
    ]
    return {
        "external_id": str(item["facility_id"]),
        "name": (item.get("name") or "").strip(),
        "address_street": (item.get("street") or "").strip(),
        "address_city": (item.get("city") or "").strip(),
        "lat": float(item["latitude"]),
        "lon": float(item["longitude"]),
        "categories": json.dumps(categories, ensure_ascii=False),
        "phone": item.get("phone"),
        "url": item.get("website"),
        "raw_json": json.dumps(item, ensure_ascii=False),
    }


def save_rows(rows: list[dict]) -> int:
    conn = get_connection()
    try:
        package_id = conn.execute(
            "SELECT id FROM packages WHERE slug = ?", (PACKAGE_SLUG,)
        ).fetchone()["id"]
        scraped_at = datetime.now(timezone.utc).isoformat()

        for row in rows:
            conn.execute(
                """
                INSERT INTO raw_facilities
                    (package_id, external_id, name, address_street, address_city,
                     lat, lon, categories, phone, url, raw_json, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(package_id, external_id) DO UPDATE SET
                    name=excluded.name,
                    address_street=excluded.address_street,
                    address_city=excluded.address_city,
                    lat=excluded.lat,
                    lon=excluded.lon,
                    categories=excluded.categories,
                    phone=excluded.phone,
                    url=excluded.url,
                    raw_json=excluded.raw_json,
                    scraped_at=excluded.scraped_at
                """,
                (
                    package_id,
                    row["external_id"],
                    row["name"],
                    row["address_street"],
                    row["address_city"],
                    row["lat"],
                    row["lon"],
                    row["categories"],
                    row["phone"],
                    row["url"],
                    row["raw_json"],
                    scraped_at,
                ),
            )
        conn.commit()
        # Not len(rows): a handful of clubs share a facility_id (e.g. the
        # same physical club listed under more than one membership tier),
        # which ON CONFLICT collapses into fewer actual rows.
        return conn.execute(
            "SELECT COUNT(*) FROM raw_facilities WHERE package_id = ?", (package_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def main() -> None:
    init_db()
    print("Fetching BeActive club list...")
    clubs = fetch_all_clubs()
    print(f"Fetched {len(clubs)} clubs nationwide.")

    # A handful of entries have no real coordinates (null latitude/longitude).
    clubs = [c for c in clubs if c.get("latitude") is not None and c.get("longitude") is not None]
    print(f"{len(clubs)} of them have real coordinates.")

    rows = [to_row(item) for item in clubs]
    saved = save_rows(rows)
    print(f"Saved/updated {saved} rows for package '{PACKAGE_SLUG}'.")


if __name__ == "__main__":
    main()
