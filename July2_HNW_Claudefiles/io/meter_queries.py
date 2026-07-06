"""
io/meter_queries.py — loads the meter-to-load SQL from sql/meter_loads.sql.

The SQL itself lives in sql/meter_loads.sql (single source of truth, editable
by anyone comfortable with SQL and runnable directly in Databricks). This module
just reads it so the Python loaders can execute it.
"""
from __future__ import annotations
import os

_SQL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "sql")


def _load(name: str) -> str:
    with open(os.path.join(_SQL_DIR, name), "r") as f:
        return f.read()


# the meter-loads query text (read once at import)
METER_LOADS = _load("meter_loads.sql")
