"""Scrapes the public Medicover Sport locations API nationwide and stores all
facilities into raw_facilities.

The API (search-api.medicoversport.pl/v1/locations) requires no auth and
supports limit/page pagination, so we just fetch every page.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from common.categories import normalize_category
from db import get_connection, init_db

BASE_URL = "https://search-api.medicoversport.pl/v1/locations"
PAGE_LIMIT = 100
REQUEST_DELAY_S = 0.2
PACKAGE_SLUG = "medicover_sport"


def fetch_all_locations() -> list[dict]:
    items: list[dict] = []
    page = 1
    total_count = None

    while total_count is None or (page - 1) * PAGE_LIMIT < total_count:
        resp = httpx.get(BASE_URL, params={"limit": PAGE_LIMIT, "page": page}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        total_count = data["total_count"]
        items.extend(data["items"])
        print(f"  page {page}/{data['page_count']} -> {len(items)}/{total_count} items")
        page += 1
        time.sleep(REQUEST_DELAY_S)

    return items


def to_row(item: dict) -> dict:
    address = item.get("address", {})
    details = item.get("details", {})
    coordinates = item.get("coordinates", {})
    categories = [normalize_category(s["name"]) for s in item.get("services", []) if s.get("name")]
    street = " ".join(
        part for part in [address.get("street"), address.get("street_number")] if part
    ).strip()

    return {
        "external_id": str(item["vid"]),
        "name": item.get("name", "").strip(),
        "address_street": street,
        "address_city": address.get("city", "").strip(),
        "lat": float(coordinates["lat"]),
        "lon": float(coordinates["lon"]),
        "categories": json.dumps(sorted(set(categories)), ensure_ascii=False),
        "phone": details.get("phone"),
        "url": details.get("www"),
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
        # Not len(rows): the source list can contain duplicate external_ids
        # (e.g. items shifting between pages while a 73-page fetch is in
        # flight), which ON CONFLICT collapses into fewer actual rows.
        return conn.execute(
            "SELECT COUNT(*) FROM raw_facilities WHERE package_id = ?", (package_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def main() -> None:
    init_db()
    print("Fetching Medicover Sport locations (nationwide, paginated)...")
    items = fetch_all_locations()
    print(f"Fetched {len(items)} locations total.")

    # A handful of entries (e.g. "ONLINE_..." remote classes) have no real
    # location and so an empty list instead of a {lat, lon} dict.
    items = [item for item in items if isinstance(item.get("coordinates"), dict)]
    print(f"{len(items)} of them have real coordinates.")

    # A handful more carry a bad coordinate from Medicover's own system (a
    # stale/test placeholder abroad, or a missing longitude defaulting to 0)
    # rather than their real address - drop anything outside Poland.
    min_lat, min_lon, max_lat, max_lon = config.POLAND_BBOX
    items = [
        item for item in items
        if min_lat <= float(item["coordinates"]["lat"]) <= max_lat
        and min_lon <= float(item["coordinates"]["lon"]) <= max_lon
    ]
    print(f"{len(items)} of them are within Poland's bounding box.")

    rows = [to_row(item) for item in items]
    saved = save_rows(rows)
    print(f"Saved/updated {saved} rows for package '{PACKAGE_SLUG}'.")


if __name__ == "__main__":
    main()
