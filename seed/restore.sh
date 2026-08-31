#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--reset" ]]; then
  echo "This replaces Agentcy's Docker database, media, and Chroma volumes."
  echo "Run: ./seed/restore.sh --reset"
  exit 2
fi

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

for path in seed/mysql/agentcy.sql seed/assets seed/chroma; do
  if [[ ! -e "$path" ]]; then
    echo "Missing $path; this checkout does not contain the complete seed."
    exit 1
  fi
done

# A clean volume makes the copied media exactly match the database references.
docker compose down -v
docker compose up -d mysql
docker compose exec -T mysql sh -lc '
  for attempt in $(seq 1 30); do
    mysqladmin ping -h localhost -uroot -pagentcy_root --silent && exit 0
    sleep 2
  done
  exit 1
'

# The dump creates and selects the application database itself.
docker compose exec -T mysql sh -lc 'mysql -uroot -pagentcy_root' < seed/mysql/agentcy.sql

# Create the stopped app container so its named volumes can be populated before
# it starts. This avoids a first-run index/write racing the copied seed data.
docker compose create app
docker compose cp seed/assets/. app:/data/assets
docker compose cp seed/chroma/. app:/data/chroma
docker compose start app

echo "Seed restored. The app is available at http://localhost:8002."
