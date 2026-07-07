"""
io/connection.py — Databricks connection from environment.

Credentials live in a local .env (never committed):
    DATABRICKS_SERVER_HOSTNAME=...
    DATABRICKS_HTTP_PATH=...
    DATABRICKS_ACCESS_TOKEN=...

Usage:
    from milsoft_dss.io.connection import get_connection
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

Design notes for the FastAPI future:
  * Stateless: each call opens a connection, the caller closes it (context mgr).
    FastAPI can wrap this in a per-request dependency, or a pool can be added
    later WITHOUT changing callers (they just ask for a connection).
  * No credentials in code — only the environment. Safe to run server-side.
"""
from __future__ import annotations
import os
from contextlib import contextmanager

try:
    from dotenv import load_dotenv
    load_dotenv()                      # load .env into os.environ once on import
except ImportError:
    pass                               # dotenv optional; env may be set another way


class MissingCredentials(RuntimeError):
    """Raised when required Databricks env vars are absent."""


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise MissingCredentials(
            f"{name} not set. Add it to your local .env "
            f"(DATABRICKS_SERVER_HOSTNAME, DATABRICKS_HTTP_PATH, "
            f"DATABRICKS_ACCESS_TOKEN)."
        )
    return val


@contextmanager
def get_connection():
    """Yield a Databricks SQL connection, closed on exit."""
    try:
        from databricks import sql
    except ImportError as e:
        raise RuntimeError(
            "databricks-sql-connector not installed. "
            "pip install databricks-sql-connector"
        ) from e

    conn = sql.connect(
        server_hostname=_require("DATABRICKS_SERVER_HOSTNAME"),
        http_path=_require("DATABRICKS_HTTP_PATH"),
        access_token=_require("DATABRICKS_ACCESS_TOKEN"),
    )
    try:
        yield conn
    finally:
        conn.close()


def query(sql_text: str, params: dict | None = None) -> list[dict]:
    """Run a read-only query, return rows as a list of dicts.

    Parameterized via named markers (:name) — NEVER string-format user input
    into SQL. This is the single choke point all loaders go through.

    Column names are LOWERCASED in the returned dicts, so the Python layer can
    use consistent lowercase keys regardless of the database's column casing
    (e.g. UPPERCASE in silver.usage_point_paths).
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text, params or {})
            cols = [d[0].lower() for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
