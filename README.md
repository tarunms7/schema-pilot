# schema-pilot
SchemaPilot generates online-safe PostgreSQL migrations from PRs. It diffs model schemas (base vs head), detects renames/add/alter/drop, plans low-lock steps (defaults→backfill→NOT NULL, FKs NOT VALID→VALIDATE, concurrent indexes), and outputs forward/rollback SQL. MVP: SQLAlchemy→Postgres; adapters extensible.
