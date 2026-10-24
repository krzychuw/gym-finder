"""Builds canonical_facilities by matching raw_facilities across providers
that represent the same physical place.

Two raw facilities from different providers are considered a match if they
are close together AND have a similar name or address - distance alone is
not enough (e.g. two different clubs in the same shopping mall), and text
similarity alone is not enough either (chain names repeat across the city).

Matched facilities are grouped with union-find, so if A matches B and B
matches C, all three end up in one canonical facility even if A and C were
never compared directly - this also means the approach generalizes to a
third, fourth, etc. provider without any changes.

This script fully rebuilds canonical_facilities and facility_links every run
(delete + reinsert) rather than diffing - simpler and safe given the data is
refreshed by hand, not continuously.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from common.geo import haversine_m
from db import get_connection, init_db


def is_match(a: dict, b: dict) -> tuple[bool, float]:
    distance = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
    if distance > config.MATCH_DISTANCE_THRESHOLD_M:
        return False, 0.0

    name_score = fuzz.token_sort_ratio(a["name"], b["name"])
    if name_score < config.MATCH_NAME_SIMILARITY_MIN:
        # Below this, names are unrelated - two different businesses that
        # happen to share a building (e.g. a big sports complex with several
        # independent tenants) must not be merged just because their address
        # string is identical.
        return False, 0.0

    address_score = fuzz.token_sort_ratio(a["address_street"] or "", b["address_street"] or "")
    if name_score >= config.MATCH_NAME_SIMILARITY_STRONG or address_score >= config.MATCH_ADDRESS_SIMILARITY_THRESHOLD:
        return True, max(name_score, address_score)
    return False, 0.0


class UnionFind:
    def __init__(self, ids):
        self.parent = {i: i for i in ids}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def load_raw_facilities(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT rf.id, rf.package_id, rf.name, rf.address_street, rf.address_city,
               rf.lat, rf.lon, rf.categories, p.slug AS package_slug
        FROM raw_facilities rf
        JOIN packages p ON p.id = rf.package_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


# Side length (in degrees) of the spatial grid cells used to bucket
# facilities before matching. At Poland's latitude this is roughly 1.1km
# (N-S) x 0.7km (E-W) - comfortably larger than MATCH_DISTANCE_THRESHOLD_M,
# so checking a facility's own cell plus its 8 neighbors can never miss a
# match. Nationwide, comparing every pair directly (combinations() over
# ~14k facilities) is ~10^8 comparisons and impractically slow; bucketing
# first cuts each facility's comparisons down to roughly how many other
# facilities sit within ~1-2km of it, which is what actually bounds whether
# two places could be the same physical location.
GRID_CELL_DEG = 0.01


def _grid_cell(facility: dict) -> tuple[int, int]:
    return (int(facility["lat"] / GRID_CELL_DEG), int(facility["lon"] / GRID_CELL_DEG))


def build_matches(facilities: list[dict]) -> dict:
    uf = UnionFind([f["id"] for f in facilities])
    scores: dict[tuple, float] = {}

    buckets: dict[tuple, list[dict]] = {}
    for f in facilities:
        buckets.setdefault(_grid_cell(f), []).append(f)

    for a in facilities:
        gx, gy = _grid_cell(a)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for b in buckets.get((gx + dx, gy + dy), []):
                    # Process each unordered pair exactly once regardless of
                    # which of the two facilities' neighborhoods finds it.
                    if b["id"] <= a["id"]:
                        continue
                    if a["package_id"] == b["package_id"]:
                        continue
                    matched, score = is_match(a, b)
                    if matched:
                        uf.union(a["id"], b["id"])
                        scores[(a["id"], b["id"])] = score

    return {"uf": uf, "scores": scores}


def group_by_root(facilities: list[dict], uf: UnionFind) -> dict:
    groups: dict = {}
    for f in facilities:
        root = uf.find(f["id"])
        groups.setdefault(root, []).append(f)
    return groups


def best_score_for(facility_id: int, group: list[dict], scores: dict) -> float | None:
    best = None
    for other in group:
        if other["id"] == facility_id:
            continue
        key = (facility_id, other["id"]) if facility_id < other["id"] else (other["id"], facility_id)
        if key in scores:
            best = max(best or 0, scores[key])
    return best


def rebuild_canonical(conn, groups: dict, scores: dict) -> dict:
    conn.execute("DELETE FROM facility_links")
    conn.execute("DELETE FROM canonical_facilities")

    now = datetime.now(timezone.utc).isoformat()
    stats = {"canonical_count": 0, "dual_package_count": 0, "dual_samples": []}

    package_priority = {pkg["slug"]: i for i, pkg in enumerate(config.PACKAGES)}

    for group in groups.values():
        group_sorted = sorted(group, key=lambda f: package_priority.get(f["package_slug"], 999))
        primary = group_sorted[0]

        lat = sum(f["lat"] for f in group) / len(group)
        lon = sum(f["lon"] for f in group) / len(group)

        categories = set()
        for f in group:
            categories.update(json.loads(f["categories"] or "[]"))

        name = next((f["name"] for f in group_sorted if f["name"]), primary["name"])
        address_street = next((f["address_street"] for f in group_sorted if f["address_street"]), None)
        address_city = next((f["address_city"] for f in group_sorted if f["address_city"]), None)

        cur = conn.execute(
            """
            INSERT INTO canonical_facilities
                (name, address_street, address_city, lat, lon, categories, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, address_street, address_city, lat, lon, json.dumps(sorted(categories), ensure_ascii=False), now),
        )
        canonical_id = cur.lastrowid
        stats["canonical_count"] += 1

        package_slugs = {f["package_slug"] for f in group}
        if len(package_slugs) > 1:
            stats["dual_package_count"] += 1
            if len(stats["dual_samples"]) < 20:
                stats["dual_samples"].append((name, address_street, sorted(package_slugs)))

        for f in group:
            score = best_score_for(f["id"], group, scores)
            conn.execute(
                "INSERT INTO facility_links (canonical_id, raw_facility_id, match_score) VALUES (?, ?, ?)",
                (canonical_id, f["id"], score),
            )

    conn.commit()
    return stats


def main() -> None:
    init_db()
    conn = get_connection()
    try:
        facilities = load_raw_facilities(conn)
        print(f"Loaded {len(facilities)} raw facilities.")
        per_package = {}
        for f in facilities:
            per_package[f["package_slug"]] = per_package.get(f["package_slug"], 0) + 1
        for slug, count in per_package.items():
            print(f"  {slug}: {count}")

        print("Matching across providers...")
        match_result = build_matches(facilities)
        groups = group_by_root(facilities, match_result["uf"])

        print("Rebuilding canonical_facilities...")
        stats = rebuild_canonical(conn, groups, match_result["scores"])

        print(f"\nCanonical facilities: {stats['canonical_count']}")
        print(f"Dual-package facilities: {stats['dual_package_count']}")
        print("\nSample dual-package matches:")
        for name, address, slugs in stats["dual_samples"]:
            print(f"  - {name} ({address}) -> {', '.join(slugs)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
