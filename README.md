# schema-pilot

SchemaPilot generates online-safe PostgreSQL migrations from PRs. It diffs model schemas (base vs head), detects renames/add/alter/drop, plans low-lock steps (defaults→backfill→NOT NULL, FKs NOT VALID→VALIDATE, concurrent indexes), and outputs forward/rollback SQL. MVP: SQLAlchemy→Postgres; adapters extensible.

## Quickstart

1. Install deps

```bash
python3 -m pip install -r requirements.txt  # or use poetry if preferred
```

2. Run demo on included examples

```bash
python3 -m schema_agent.cli \
  --base-dir ./examples/before --base-module examples.before.models \
  --head-dir ./examples/after  --head-module  examples.after.models \
  --dialect postgresql \
  --out-dir ./artifacts
```

3. Run tests

```bash
python3 -m pytest -q
```

## Overview

This tool builds an IR from models (MVP: SQLAlchemy), diffs two trees, plans safe online migrations for Postgres, and emits forward and rollback SQL.
