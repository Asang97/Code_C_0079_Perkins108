-- =====================================================================
-- WindMil Topology — PURE SQL for Databricks SQL Editor
-- Each numbered block is self-contained: select it and Run.
-- Set the snapshot ONCE (block 0), then run any block below.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0)  SET THE SNAPSHOT  (run this first, on its own)
-- ---------------------------------------------------------------------
DECLARE OR REPLACE VARIABLE snap STRING DEFAULT '260316_std';
-- See what snapshots exist:
--   SELECT DISTINCT _snapshot_folder FROM peng_windmil_source ORDER BY 1 DESC;
-- Change with:  SET VARIABLE snap = '251006_std';


-- ---------------------------------------------------------------------
-- 1)  RADIAL TEST  — any element with >1 distinct parent in this snapshot
--     Empty result = strictly radial.
-- ---------------------------------------------------------------------
WITH edges AS (
            SELECT element_name, parent_element_name FROM peng_windmil_source            WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name FROM peng_windmil_overhead_line      WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name FROM peng_windmil_underground_line   WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name FROM peng_windmil_step_transformer   WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name FROM peng_windmil_electric_switch    WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name FROM peng_windmil_overcurrent_device WHERE _snapshot_folder = snap
)
SELECT element_name, COUNT(DISTINCT parent_element_name) AS parent_count
FROM edges
GROUP BY element_name
HAVING COUNT(DISTINCT parent_element_name) > 1
ORDER BY parent_count DESC;


-- ---------------------------------------------------------------------
-- 2)  ORPHANS  — parent reference that resolves to nothing (not ROOT)
-- ---------------------------------------------------------------------
WITH edges AS (
            SELECT element_name, parent_element_name, 'source'             AS etype FROM peng_windmil_source            WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'overhead_line'           FROM peng_windmil_overhead_line      WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'underground_line'        FROM peng_windmil_underground_line   WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'step_transformer'        FROM peng_windmil_step_transformer   WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'electric_switch'         FROM peng_windmil_electric_switch    WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'overcurrent_device'      FROM peng_windmil_overcurrent_device WHERE _snapshot_folder = snap
)
SELECT e.element_name, e.parent_element_name, e.etype
FROM edges e
LEFT JOIN edges p ON e.parent_element_name = p.element_name
WHERE e.parent_element_name <> 'ROOT' AND p.element_name IS NULL;


-- ---------------------------------------------------------------------
-- 3)  SOURCES  — feeder roots (parent = ROOT)
-- ---------------------------------------------------------------------
WITH edges AS (
            SELECT element_name, parent_element_name, phase_config_code FROM peng_windmil_source            WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, phase_config_code FROM peng_windmil_overhead_line      WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, phase_config_code FROM peng_windmil_underground_line   WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, phase_config_code FROM peng_windmil_step_transformer   WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, phase_config_code FROM peng_windmil_electric_switch    WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, phase_config_code FROM peng_windmil_overcurrent_device WHERE _snapshot_folder = snap
)
SELECT element_name AS feeder_root, phase_config_code
FROM edges WHERE parent_element_name = 'ROOT'
ORDER BY 1;


-- ---------------------------------------------------------------------
-- 4)  FEEDER ASSIGNMENT + SUMMARY  (the partitioner, recursive)
--     Walks each source down its radial tree; element -> feeder_root + depth.
-- ---------------------------------------------------------------------
WITH RECURSIVE edges AS (
            SELECT element_name, parent_element_name, 'source'             AS etype FROM peng_windmil_source            WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'overhead_line'           FROM peng_windmil_overhead_line      WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'underground_line'        FROM peng_windmil_underground_line   WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'step_transformer'        FROM peng_windmil_step_transformer   WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'electric_switch'         FROM peng_windmil_electric_switch    WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'overcurrent_device'      FROM peng_windmil_overcurrent_device WHERE _snapshot_folder = snap
),
tree AS (
    SELECT element_name, parent_element_name, etype,
           element_name AS feeder_root, 0 AS depth
    FROM edges WHERE parent_element_name = 'ROOT'
  UNION ALL
    SELECT c.element_name, c.parent_element_name, c.etype,
           t.feeder_root, t.depth + 1
    FROM edges c JOIN tree t ON c.parent_element_name = t.element_name
)
SELECT feeder_root,
       COUNT(*)   AS n_elements,
       MAX(depth) AS max_depth
FROM tree
GROUP BY feeder_root
ORDER BY n_elements DESC;


-- ---------------------------------------------------------------------
-- 4b) FULL MEMBERSHIP  — every element with its feeder + depth
--     (same recursion; remove the GROUP BY to see element-level rows)
-- ---------------------------------------------------------------------
WITH RECURSIVE edges AS (
            SELECT element_name, parent_element_name, 'source'             AS etype FROM peng_windmil_source            WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'overhead_line'           FROM peng_windmil_overhead_line      WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'underground_line'        FROM peng_windmil_underground_line   WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'step_transformer'        FROM peng_windmil_step_transformer   WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'electric_switch'         FROM peng_windmil_electric_switch    WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'overcurrent_device'      FROM peng_windmil_overcurrent_device WHERE _snapshot_folder = snap
),
tree AS (
    SELECT element_name, parent_element_name, etype,
           element_name AS feeder_root, 0 AS depth
    FROM edges WHERE parent_element_name = 'ROOT'
  UNION ALL
    SELECT c.element_name, c.parent_element_name, c.etype,
           t.feeder_root, t.depth + 1
    FROM edges c JOIN tree t ON c.parent_element_name = t.element_name
)
SELECT element_name, parent_element_name, etype, feeder_root, depth
FROM tree
ORDER BY feeder_root, depth, element_name;


-- ---------------------------------------------------------------------
-- 5)  COVERAGE  — elements NOT reachable from any source (islands)
--     Reuses the recursion, then anti-joins against all edges.
-- ---------------------------------------------------------------------
WITH RECURSIVE edges AS (
            SELECT element_name, parent_element_name, 'source'             AS etype FROM peng_windmil_source            WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'overhead_line'           FROM peng_windmil_overhead_line      WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'underground_line'        FROM peng_windmil_underground_line   WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'step_transformer'        FROM peng_windmil_step_transformer   WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'electric_switch'         FROM peng_windmil_electric_switch    WHERE _snapshot_folder = snap
  UNION ALL SELECT element_name, parent_element_name, 'overcurrent_device'      FROM peng_windmil_overcurrent_device WHERE _snapshot_folder = snap
),
tree AS (
    SELECT element_name FROM edges WHERE parent_element_name = 'ROOT'
  UNION ALL
    SELECT c.element_name
    FROM edges c JOIN tree t ON c.parent_element_name = t.element_name
)
SELECT e.element_name, e.parent_element_name, e.etype
FROM edges e
LEFT JOIN tree t ON e.element_name = t.element_name
WHERE t.element_name IS NULL;
