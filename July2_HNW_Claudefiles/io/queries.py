"""
io/queries.py — loads the parameterized SQL from the sql/ folder.

All query text lives in sql/*.sql (single source of truth, runnable directly in
Databricks). This module reads them so the loaders can execute them. Bronze/
silver only — no semantic schema.
"""
from __future__ import annotations
import os

_SQL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "sql",
)


def _load(name: str) -> str:
    with open(os.path.join(_SQL_DIR, name), "r") as f:
        return f.read()


LIST_SNAPSHOTS      = _load("list_snapshots.sql")
LIST_FEEDERS        = _load("list_feeders.sql")
FEEDER_ELEMENTS     = _load("feeder_elements.sql")
FEEDER_LINES        = _load("feeder_lines.sql")
FEEDER_TRANSFORMERS = _load("feeder_transformers.sql")
FEEDER_SOURCE       = _load("feeder_source.sql")
METER_LOADS         = _load("meter_loads.sql")
