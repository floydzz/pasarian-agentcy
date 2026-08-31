# Agentcy seed snapshot — 2026-08-31

This directory is a checked-in, reproducible snapshot of the current Agentcy
demo state. It is intentionally data-only: it contains no `.env` file,
provider credentials, or API keys.

It includes:

- `mysql/agentcy.sql` — the MySQL schema and all current application records,
  including campaigns, History, asset metadata, and trailer metadata.
- `assets/` — the generated images, videos, uploaded references, and trailer
  media named by the database's `/media/...` URLs.
- `chroma/` — the current local Chroma vector index.
- `MANIFEST.sha256` — integrity hashes for every seed file.

The media is deliberately stored outside `backend/data/assets/`, which remains
runtime storage and is ignored by Git. `restore.sh` copies this versioned seed
into the Docker volumes used by the app.

## Restore the exact snapshot

From the repository root, run:

```bash
./seed/restore.sh --reset
```

This removes the project's existing Docker volumes before restoring the
snapshot. It does not touch `.env`; copy `.env.example` first if you need a
local configuration. The seeded app works with the default demo providers.

To verify an existing checked-out seed before restoring it:

```bash
shasum -a 256 -c seed/MANIFEST.sha256
```

## Scope

This snapshot is a point-in-time demo baseline, not a live backup system.
New generated media and database changes remain local until a new seed
snapshot is deliberately created.
