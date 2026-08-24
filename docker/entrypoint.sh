#!/bin/sh
# Bring the container up to a state where the demo can start, then hand over.
#
# Deliberately idempotent: `docker compose up` on a machine that has already run
# it must be a no-op, not a re-migration and not a second round of embedding
# bills. Everything here is safe to run on every boot.
set -e

echo "→ waiting for the database"
python scripts/wait_for_db.py "${DB_WAIT_SECONDS:-60}"

echo "→ creating any missing tables"
python scripts/init_db.py

if [ "${SKIP_INGEST:-0}" = "1" ]; then
  echo "→ skipping ingestion (SKIP_INGEST=1)"
else
  echo "→ ingesting the corpora"
  python scripts/ingest_kb.py --if-empty
fi

echo "→ starting: $*"
exec "$@"
