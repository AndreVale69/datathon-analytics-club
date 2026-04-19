#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

sudo tailscale funnel reset
docker compose stop web api

echo "Stopped public demo and closed the funnel."
