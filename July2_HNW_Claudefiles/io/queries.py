"""
io/queries.py — loads the parameterized SQL from the sql/ folder.

All query text lives in sql/*.sql (single source of truth, runnable directly in
Databricks). This module reads them so the loaders can execute them. Bronze/
silver only — no semantic schema.
"""
from __future__ import annotations
import os

# Resolve the sql/ folder robustly. Checks, in order:
#   1. MILSOFT_SQL_DIR env var (explicit override)
#   2. <repo_root>/sql   (repo root = parent of the milsoft_dss package)
#   3. <package>/sql     (sql/ inside the package)
#   4. ./sql             (current working directory)
_HERE = os.path.dirname(os.path.abspath(__file__))              # milsoft_dss/io
_PKG = os.path.dirname(_HERE)                                    # milsoft_dss
_REPO = os.path.dirname(_PKG)                                    # repo root

_CANDIDATES = [
    os.environ.get("MILSOFT_SQL_DIR"),
    os.path.join(_REPO, "sql"),
    os.path.join(_PKG, "sql"),
    os.path.join(os.getcwd(), "sql"),
]


def _sql_dir() -> str:
    for c in _CANDIDATES:
        if c and os.path.isdir(c):
            return c
    tried = "\n  ".join(str(c) for c in _CANDIDATES if c)
    raise FileNotFoundError(
        "Could not find the sql/ folder. Place the .sql files in a 'sql/' "
        "directory next to the milsoft_dss package, or set MILSOFT_SQL_DIR.\n"
        f"Looked in:\n  {tried}"
    )


def _load(name: str) -> str:
    path = os.path.join(_sql_dir(), name)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"SQL file '{name}' not found in {_sql_dir()}. "
            f"Ensure all .sql files are present."
        )
    with open(path, "r") as f:
        sql = f.read()
    # inject the catalog (top folder) from config/env; set once.
    catalog = os.environ.get("MILSOFT_CATALOG", "")
    if "{catalog}" in sql:
        if not catalog:
            raise RuntimeError(
                "SQL references {catalog} but MILSOFT_CATALOG is not set. "
                "Add MILSOFT_CATALOG=<your_catalog> to your .env."
            )
        sql = sql.replace("{catalog}", catalog)
    return sql


LIST_SNAPSHOTS      = _load("list_snapshots.sql")
LIST_FEEDERS        = _load("list_feeders.sql")
FEEDER_ELEMENTS     = _load("feeder_elements.sql")
FEEDER_LINES        = _load("feeder_lines.sql")
FEEDER_TRANSFORMERS = _load("feeder_transformers.sql")
FEEDER_SOURCE       = _load("feeder_source.sql")
METER_LOADS         = _load("meter_loads.sql")
