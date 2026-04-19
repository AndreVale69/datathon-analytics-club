#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-.env.local}"

cd "$ROOT_DIR"

if [[ ! -d raw_data ]]; then
  echo "raw_data/ is missing. Restore the dataset before starting the public demo." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required." >&2
  exit 1
fi

if ! command -v tailscale >/dev/null 2>&1; then
  echo "tailscale is required." >&2
  exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
  echo "Starting compose stack with env file: $ENV_FILE"
  docker compose --env-file "$ENV_FILE" up -d --build api web
else
  echo "Env file $ENV_FILE not found, starting with current shell environment"
  docker compose up -d --build api web
fi

echo "Opening Tailscale Funnel on port 8080"
sudo tailscale funnel --bg 8080

echo
echo "Public status:"
tailscale funnel status
echo
echo "Expected endpoints:"
echo "  UI:  https://<funnel-url>/"
echo "  API: https://<funnel-url>/listings"
