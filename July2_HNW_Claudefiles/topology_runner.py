"""
WindMil topology builder — thin Python orchestration over SQL-first logic.
The graph traversal lives in the recursive CTE; Python just sets the snapshot,
runs the queries, and returns the results. Swap the DuckDB connection for your
Databricks SQLAlchemy/connector engine.
"""
from dataclasses import dataclass

ELEMENT_TABLES = [
    ("peng_windmil_source",             "source"),
    ("peng_windmil_overhead_line",      "overhead_line"),
    ("peng_windmil_underground_line",   "underground_line"),
    ("peng_windmil_step_transformer",   "step_transformer"),
    ("peng_windmil_electric_switch",    "electric_switch"),
    ("peng_windmil_overcurrent_device", "overcurrent_device"),
]

def _edges_sql(snap: str) -> str:
    # snap is validated against the known-snapshot allowlist before use.
    parts = [
        f"SELECT element_name, parent_element_name, '{etype}' AS etype, "
        f"phase_config_code FROM {tbl} WHERE _snapshot_folder = '{snap}'"
        for tbl, etype in ELEMENT_TABLES
    ]
    return "\nUNION ALL ".join(parts)

def list_snapshots(con) -> list[str]:
    return [r[0] for r in con.execute(
        "SELECT DISTINCT _snapshot_folder FROM peng_windmil_source ORDER BY 1 DESC"
    ).fetchall()]

def build_topology(con, snap: str) -> dict:
    snaps = list_snapshots(con)
    if snap not in snaps:
        raise ValueError(f"snapshot {snap!r} not in {snaps}")

    con.execute(f"CREATE OR REPLACE VIEW edges AS {_edges_sql(snap)}")

    mesh = con.execute("""
        SELECT element_name, COUNT(DISTINCT parent_element_name) pc
        FROM edges GROUP BY element_name HAVING COUNT(DISTINCT parent_element_name) > 1
    """).df()

    orphans = con.execute("""
        SELECT e.element_name, e.parent_element_name, e.etype
        FROM edges e LEFT JOIN edges p ON e.parent_element_name = p.element_name
        WHERE e.parent_element_name <> 'ROOT' AND p.element_name IS NULL
    """).df()

    con.execute("""
        CREATE OR REPLACE TABLE feeder_membership AS
        WITH RECURSIVE tree AS (
            SELECT element_name, parent_element_name, etype,
                   element_name AS feeder_root, 0 AS depth
            FROM edges WHERE parent_element_name = 'ROOT'
          UNION ALL
            SELECT c.element_name, c.parent_element_name, c.etype,
                   t.feeder_root, t.depth+1
            FROM edges c JOIN tree t ON c.parent_element_name = t.element_name
        ) SELECT * FROM tree
    """)

    feeders = con.execute("""
        SELECT feeder_root, COUNT(*) n_elements, MAX(depth) max_depth
        FROM feeder_membership GROUP BY feeder_root ORDER BY n_elements DESC
    """).df()

    unreachable = con.execute("""
        SELECT e.element_name, e.parent_element_name, e.etype
        FROM edges e LEFT JOIN feeder_membership f ON e.element_name=f.element_name
        WHERE f.element_name IS NULL
    """).df()

    return {
        "snapshot": snap,
        "n_feeders": len(feeders),
        "is_radial": len(mesh) == 0,
        "feeders": feeders,
        "mesh_violations": mesh,
        "orphans": orphans,
        "unreachable": unreachable,
    }

if __name__ == "__main__":
    import duckdb
    con = duckdb.connect("synth.db")
    print("available snapshots:", list_snapshots(con))
    r = build_topology(con, "260316_std")
    print(f"\nsnapshot={r['snapshot']}  radial={r['is_radial']}  feeders={r['n_feeders']}")
    print(f"mesh_violations={len(r['mesh_violations'])}  orphans={len(r['orphans'])}  unreachable={len(r['unreachable'])}")
    print("\nfeeders:")
    print(r["feeders"].to_string(index=False))
