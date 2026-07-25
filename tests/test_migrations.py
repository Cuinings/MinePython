# -*- coding: utf-8 -*-
"""P2-1 — verify the database is brought under Alembic control on init.

Covers both ways the schema gets created:
  * the production path: ``init_db()`` create_all + stamp head (no data lost),
  * the raw CLI path: ``alembic upgrade head`` against a fresh database.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from modules.user.database import engine, init_db

ROOT = Path(__file__).parent.parent
EXPECTED_TABLES = {
    "users", "refresh_tokens", "files", "audit_log",
    "roles", "permissions", "role_permissions", "alembic_version",
    "ext_category",
}


def _head_revision() -> str:
    """Return the revision id of the current Alembic head (latest migration)."""
    versions = ROOT / "migrations" / "versions"
    revs: dict[str, object] = {}
    for f in sorted(versions.glob("*.py")):
        if f.stem == "__init__":
            continue
        spec = importlib.util.spec_from_file_location("migration_" + f.stem, f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        rev = getattr(mod, "revision", None)
        down = getattr(mod, "down_revision", None)
        if rev:
            revs[rev] = down
    children = {d for d in revs.values() if d}
    heads = [r for r in revs if r not in children]
    assert len(heads) == 1, f"expected exactly one head, got {heads}"
    return heads[0]


def test_alembic_baseline_tables_present():
    init_db()
    names = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES <= names, f"missing tables: {EXPECTED_TABLES - names}"


def test_alembic_version_stamped_to_head():
    init_db()
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert stored == _head_revision(), (stored, _head_revision())


def test_alembic_upgrade_idempotent():
    """Re-running upgrade after init_db must be a safe no-op (no error)."""
    from alembic import command
    from alembic.config import Config

    init_db()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    command.upgrade(cfg, "head")  # must not raise

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar()
        stored = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert count == 1
    assert stored == _head_revision()


def test_alembic_cli_upgrade_fresh_db(tmp_path):
    """The migration itself (not create_all) builds a correct fresh schema."""
    fresh_db = tmp_path / "fresh.db"
    env = dict(os.environ)
    env["DB_PATH"] = str(fresh_db)
    env["PYTHONPATH"] = str(ROOT)

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    eng = create_engine(f"sqlite:///{fresh_db}")
    names = set(inspect(eng).get_table_names())
    assert {"users", "files", "alembic_version"} <= names, names
    with eng.connect() as conn:
        stored = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert stored == _head_revision()
