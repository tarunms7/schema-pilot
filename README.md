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

## GitHub Actions usage (on PRs)

Add a workflow like this in your application repo:

```yaml
name: schema-agent
on:
  pull_request:
    types: [opened, synchronize, reopened]
jobs:
  plan-migration:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - name: Install schema-pilot
        run: |
          python -m pip install --upgrade pip
          python -m pip install git+https://github.com/tarunms7/schema-pilot.git
      - name: Capture head/base
        run: |
          echo "HEAD_PATH=$GITHUB_WORKSPACE" >> $GITHUB_ENV
          mkdir -p $RUNNER_TEMP/base
          git --work-tree=$RUNNER_TEMP/base checkout ${{ github.event.pull_request.base.sha }} -- .
          echo "BASE_PATH=$RUNNER_TEMP/base" >> $GITHUB_ENV
      - name: Run schema-agent
        run: |
          mkdir -p artifacts
          python -m schema_agent.cli \
            --base-dir "$BASE_PATH" --base-module app.db.base \
            --head-dir "$HEAD_PATH" --head-module app.db.base \
            --dialect postgresql \
            --out-dir artifacts
      - uses: actions/upload-artifact@v4
        with:
          name: schema-agent-sql
          path: |
            artifacts/forward.sql
            artifacts/rollback.sql
```

Notes:

- Ensure your module hint (e.g., `app.db.base`) imports all model modules so `Base.metadata` is populated.
- The adapter isolates imports per tree; avoid global side-effects in model imports.
