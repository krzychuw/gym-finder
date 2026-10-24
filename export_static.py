"""Exports the matched facility data from SQLite into plain JSON files under
static/data/, so the frontend can be hosted as static files with no backend
server at all - the browser just fetches these JSON files directly.

Run this after match.py (i.e. as the last step of refresh_data.sh) and
whenever you want to re-publish the static site with fresh data.
"""

import json
from pathlib import Path

import config
from db import get_connection, init_db

STATIC_DATA_DIR = config.BASE_DIR / "static" / "data"


def export_packages(conn) -> list[dict]:
    rows = conn.execute("SELECT slug, display_name FROM packages ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def load_name_overrides() -> list[dict]:
    """Manual display-name overrides, matched by original (name, address) pair
    rather than canonical_facilities.id, since match.py fully rebuilds that
    table (and its ids) on every re-scrape/re-match - an override keyed by id
    would silently stop applying, or worse, land on a different facility that
    happened to get the same id. Matching requires both name and address, not
    address alone, because multiple independent businesses can share one
    building address (see match.py's is_match docstring)."""
    if not config.FACILITY_OVERRIDES_PATH.exists():
        return []
    return json.loads(config.FACILITY_OVERRIDES_PATH.read_text())


def export_facilities(conn) -> list[dict]:
    pkg_rows = conn.execute(
        """
        SELECT fl.canonical_id, p.slug
        FROM facility_links fl
        JOIN raw_facilities rf ON rf.id = fl.raw_facility_id
        JOIN packages p ON p.id = rf.package_id
        """
    ).fetchall()
    canonical_packages: dict[int, list[str]] = {}
    for row in pkg_rows:
        canonical_packages.setdefault(row["canonical_id"], []).append(row["slug"])

    rows = conn.execute(
        "SELECT id, name, address_street, address_city, lat, lon, categories FROM canonical_facilities"
    ).fetchall()

    facilities = []
    for row in rows:
        facilities.append(
            {
                "id": row["id"],
                "name": row["name"],
                "address": " ".join(
                    part for part in [row["address_street"], row["address_city"]] if part
                ),
                "lat": row["lat"],
                "lon": row["lon"],
                "categories": json.loads(row["categories"] or "[]"),
                "packages": sorted(canonical_packages.get(row["id"], [])),
            }
        )
    overrides = load_name_overrides()
    for f in facilities:
        for override in overrides:
            if f["name"] == override["match_name"] and f["address"] == override["match_address"]:
                f["name"] = override["name"]
                break

    facilities.sort(key=lambda f: f["name"])
    return facilities


def main() -> None:
    init_db()
    conn = get_connection()
    try:
        packages = export_packages(conn)
        facilities = export_facilities(conn)
        categories = sorted({c for f in facilities for c in f["categories"]})
    finally:
        conn.close()

    STATIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DATA_DIR / "packages.json").write_text(json.dumps(packages, ensure_ascii=False))
    (STATIC_DATA_DIR / "categories.json").write_text(json.dumps(categories, ensure_ascii=False))
    (STATIC_DATA_DIR / "facilities.json").write_text(json.dumps(facilities, ensure_ascii=False))

    print(f"Exported {len(packages)} packages, {len(categories)} categories, {len(facilities)} facilities")
    print(f"-> {STATIC_DATA_DIR}")


if __name__ == "__main__":
    main()
