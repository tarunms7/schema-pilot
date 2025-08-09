from pathlib import Path
import subprocess
import sys


def test_cli_generates_sql(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    out_dir = tmp_path / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "schema_agent.cli",
        "--base-dir",
        str(root / "examples/before"),
        "--base-module",
        "examples.before.models",
        "--head-dir",
        str(root / "examples/after"),
        "--head-module",
        "examples.after.models",
        "--dialect",
        "postgresql",
        "--out-dir",
        str(out_dir),
    ]
    subprocess.check_call(cmd)

    fsql = (out_dir / "forward.sql").read_text()
    rsql = (out_dir / "rollback.sql").read_text()

    # Expect create table for orders and created_at sequence for users
    assert "CREATE TABLE IF NOT EXISTS orders" in fsql
    assert "ALTER TABLE users ALTER COLUMN created_at SET DEFAULT now();" in fsql
    assert "UPDATE users SET created_at = now() WHERE created_at IS NULL;" in fsql
    assert "ALTER TABLE users ALTER COLUMN created_at SET NOT NULL;" in fsql

    # Rollback should include users column teardown and orders drop
    assert "DROP TABLE IF EXISTS orders;" in rsql
    assert "ALTER TABLE users DROP COLUMN IF EXISTS created_at;" in rsql


