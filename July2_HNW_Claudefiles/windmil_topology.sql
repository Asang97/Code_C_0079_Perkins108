-- =====================================================================
-- WindMil Topology Builder  —  single snapshot, SQL-first
-- Target: Databricks SQL (also runs on DuckDB)
-- Set the snapshot once. Every query is scoped to it.
-- =====================================================================
-- Databricks session variable (set once, reused everywhere):
--   DECLARE OR REPLACE VARIABLE snap STRING DEFAULT '260316_std';
-- Or use a notebook widget:
--   CREATE WIDGET DROPDOWN snap DEFAULT '260316_std'
--     CHOICES (SELECT DISTINCT _snapshot_folder FROM peng_windmil_source);
-- Then reference :snap (widget) or snap (variable) below.
-- =====================================================================

-- 0) Unified edge set for ONE snapshot -------------------------------
--    One row per element: element_name, parent, type, phasing.
--    Add/remove element tables here to match your full set.
CREATE OR REPLACE TEMP VIEW edges AS
          SELECT element_name, parent_element_name, 'source'             AS etype, phase_config_code FROM peng_windmil_source            WHERE _snapshot_folder = snap
UNION ALL SELECT element_name, parent_element_name, 'overhead_line',      phase_config_code FROM peng_windmil_overhead_line      WHERE _snapshot_folder = snap
UNION ALL SELECT element_name, parent_element_name, 'underground_line',   phase_config_code FROM peng_windmil_underground_line   WHERE _snapshot_folder = snap
UNION ALL SELECT element_name, parent_element_name, 'step_transformer',   phase_config_code FROM peng_windmil_step_transformer   WHERE _snapshot_folder = snap
UNION ALL SELECT element_name, parent_element_name, 'electric_switch',    phase_config_code FROM peng_windmil_electric_switch    WHERE _snapshot_folder = snap
UNION ALL SELECT element_name, parent_element_name, 'overcurrent_device', phase_config_code FROM peng_windmil_overcurrent_device WHERE _snapshot_folder = snap
;

-- 1) RADIAL TEST: any element with >1 distinct parent in this snapshot.
--    Empty result = strictly radial. (Run UNSCOPED and you'll see the
--    cross-snapshot artifact; scoped, it should be empty.)
SELECT element_name, COUNT(DISTINCT parent_element_name) AS parent_count
FROM edges
GROUP BY element_name
HAVING COUNT(DISTINCT parent_element_name) > 1
ORDER BY parent_count DESC;

-- 2) ORPHANS: parent reference that resolves to nothing (and isn't ROOT).
SELECT e.element_name, e.parent_element_name, e.etype
FROM edges e
LEFT JOIN edges p ON e.parent_element_name = p.element_name
WHERE e.parent_element_name <> 'ROOT' AND p.element_name IS NULL;

-- 3) SOURCES = feeder roots (parent = ROOT).
SELECT element_name AS feeder_root, phase_config_code
FROM edges WHERE parent_element_name = 'ROOT'
ORDER BY 1;

-- 4) FEEDER ASSIGNMENT (the partitioner): recursive walk from each
--    source down its radial tree. Every element -> its feeder_root + depth.
CREATE OR REPLACE TEMP VIEW feeder_membership AS
WITH RECURSIVE tree AS (
    SELECT element_name, parent_element_name, etype,
           element_name AS feeder_root, 0 AS depth
    FROM edges WHERE parent_element_name = 'ROOT'
  UNION ALL
    SELECT c.element_name, c.parent_element_name, c.etype,
           t.feeder_root, t.depth + 1
    FROM edges c
    JOIN tree t ON c.parent_element_name = t.element_name
)
SELECT * FROM tree;

-- 4a) Per-feeder summary: size + depth.
SELECT feeder_root, COUNT(*) AS n_elements, MAX(depth) AS max_depth
FROM feeder_membership
GROUP BY feeder_root
ORDER BY n_elements DESC;

-- 5) COVERAGE: elements not reachable from any source (islands/orphans).
SELECT e.element_name, e.parent_element_name, e.etype
FROM edges e
LEFT JOIN feeder_membership f ON e.element_name = f.element_name
WHERE f.element_name IS NULL;

-- 6) Element-type composition across feeders.
SELECT etype, COUNT(*) AS n FROM feeder_membership GROUP BY etype ORDER BY n DESC;
