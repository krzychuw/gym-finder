"""Scrapes the public Medicover Sport locations API and stores facilities
located in config.CITY_NAME into raw_facilities.

The API (search-api.medicoversport.pl/v1/locations) requires no auth and
supports limit/page pagination, but ignores any city filter param - so we
fetch every page (nationwide) and filter by address.city locally.
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
        return len(rows)
    finally:
        conn.close()


def main() -> None:
    init_db()
    print("Fetching Medicover Sport locations (nationwide, paginated)...")
    items = fetch_all_locations()
    print(f"Fetched {len(items)} locations total.")

    warsaw_items = [
        item for item in items
        if item.get("address", {}).get("city", "").strip().lower() == config.CITY_NAME.lower()
    ]
    print(f"{len(warsaw_items)} of them are in {config.CITY_NAME}.")

    # A handful of entries (e.g. "ONLINE_..." remote classes) have no real
    # location and so an empty list instead of a {lat, lon} dict.
    warsaw_items = [item for item in warsaw_items if isinstance(item.get("coordinates"), dict)]
    print(f"{len(warsaw_items)} of them have real coordinates.")

    rows = [to_row(item) for item in warsaw_items]
    saved = save_rows(rows)
    print(f"Saved/updated {saved} rows for package '{PACKAGE_SLUG}'.")


if __name__ == "__main__":
    main()
