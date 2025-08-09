#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)

python3 -m schema_agent.cli \
  --base-dir "$ROOT_DIR/examples/before" --base-module examples.before.models \
  --head-dir "$ROOT_DIR/examples/after"  --head-module  examples.after.models \
  --dialect postgresql \
  --out-dir "$ROOT_DIR/artifacts"

echo "Artifacts written to $ROOT_DIR/artifacts"


