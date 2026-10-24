"""Scrapes Multisport facilities nationwide using a real headless browser
session.

The underlying API (bam.benefitsystems.online/bam/search/.../sport-facilities/list)
sits behind bot-detection that rejects plain HTTP requests (even ones that
copy every header a browser would send) with a 403, and also rejects
"foreign" fetch() calls made from within a real browser page if they weren't
triggered by genuine UI interaction. So instead of calling the API directly,
this script drives the real search page like a user would: it loads the
search view and repeatedly scrolls the results list, which is what makes the
page's own code fire the paginated API calls - and just listens in on the
JSON responses as they go by.

The API filters results to whatever the map's current viewport covers, not
just the visible/loaded page - so a single pass at a country-wide zoom level
(centered on Poland, zoom 6) reports the *national* totalCount (confirmed
experimentally: ~6979) and the same scroll-to-paginate trick captures all of
it, no per-city tiling needed.

Confirmed experimentally: setting `scrollTop = scrollHeight` on
`ul.map-side-drawer__list` triggers the next page load; stopping once the
running unique count reaches the API's own `totalCount` reliably captured
all facilities in testing.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from db import get_connection, init_db

SEARCH_URL = (
    "https://www.kartamultisport.pl/multisport/wyszukiwarka-obiektow"
    f"#/@{config.POLAND_CENTER['lat']},{config.POLAND_CENTER['lon']},6z?cards=1"
)
LIST_SELECTOR = "ul.map-side-drawer__list"
PACKAGE_SLUG = "multisport"
MAX_SCROLL_ITERATIONS = 700
STABLE_ITERATIONS_TO_STOP = 8


def scrape_facilities() -> list[dict]:
    facilities: dict[str, dict] = {}
    state = {"total_count": None}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        def on_response(response):
            if "sport-facilities/list" not in response.url:
                return
            try:
                if response.status != 200:
                    print(f"  WARNING: non-200 response ({response.status}) for {response.url}")
                    return
                body = response.json()
            except Exception as exc:
                print(f"  WARNING: could not parse response as JSON: {exc}")
                return
            state["total_count"] = body.get("totalCount")
            items = body.get("sportFacilities", [])
            for item in items:
                facilities[item["id"]] = item
            print(f"  +{len(items)} -> {len(facilities)} unique so far (API totalCount={state['total_count']})")

        page.on("response", on_response)

        print(f"Navigating to {SEARCH_URL} ...")
        page.goto(SEARCH_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        list_el = page.locator(LIST_SELECTOR)
        prev_count = len(facilities)
        stable_iterations = 0
        for _ in range(MAX_SCROLL_ITERATIONS):
            if state["total_count"] is not None and len(facilities) >= state["total_count"]:
                print("Reached API's reported total count.")
                break
            list_el.evaluate("el => el.scrollTop = el.scrollHeight")
            page.wait_for_timeout(1000)
            if len(facilities) == prev_count:
                stable_iterations += 1
            else:
                stable_iterations = 0
            prev_count = len(facilities)
            if stable_iterations >= STABLE_ITERATIONS_TO_STOP:
                print(f"No new results for {STABLE_ITERATIONS_TO_STOP} scrolls, stopping.")
                break

        browser.close()

    return list(facilities.values())


def to_row(item: dict) -> dict:
    lat, lon = item["geopoint"]
    return {
        "external_id": str(item["id"]),
        "name": item.get("name", "").strip(),
        "address_street": (item.get("address") or "").strip(),
        "address_city": (item.get("city") or "").strip(),
        "lat": float(lat),
        "lon": float(lon),
        # Multisport's category/parameter filters are only exposed as
        # opaque numeric ids in this API (no dictionary endpoint was found
        # that maps them to names), so we don't attempt to translate them.
        # Category filtering in the app is driven by whichever provider
        # *does* supply readable categories (currently Medicover Sport).
        "categories": json.dumps([], ensure_ascii=False),
        "phone": None,
        "url": None,
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
        return conn.execute(
            "SELECT COUNT(*) FROM raw_facilities WHERE package_id = ?", (package_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def main() -> None:
    init_db()
    print("Scraping Multisport facilities via browser automation...")
    items = scrape_facilities()
    print(f"Captured {len(items)} facilities.")

    config.DATA_DIR.mkdir(exist_ok=True)
    config.MULTISPORT_DUMP_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2))
    print(f"Raw dump written to {config.MULTISPORT_DUMP_PATH}")

    rows = [to_row(item) for item in items]
    saved = save_rows(rows)
    print(f"Saved/updated {saved} rows for package '{PACKAGE_SLUG}'.")


if __name__ == "__main__":
    main()
