#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/static"

echo "Otwórz w przeglądarce: http://localhost:8080"
python3 -m http.server 8080
