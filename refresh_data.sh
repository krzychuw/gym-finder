#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

.venv/bin/python -m scrapers.scrape_medicover
.venv/bin/python -m scrapers.scrape_multisport
.venv/bin/python -m scrapers.scrape_beactive
.venv/bin/python match.py
.venv/bin/python export_static.py
