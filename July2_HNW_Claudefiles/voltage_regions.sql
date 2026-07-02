-- =====================================================================
-- VOLTAGE REGION SEPARATION  —  Databricks SQL, single snapshot
-- Radial network: cut the graph at transformers; each resulting region
-- is one voltage level. A region's voltage = the secondary (load-side)
-- kV of the transformer feeding it, or the source voltage for the top region.
--
-- Inputs (silver):
--   silver.network_edges        : source_node_id, target_node_id, edge_type, VALID_FROM/TO
--   silver.network_transformers  : node_id, rated_voltage_loadside  (secondary kV)
--   silver.network_substations   : node_id, nominal_voltage         (source kV)
-- Adjust table/column names to your schema as needed.
--
-- Set the as-of date once (single-version selection via validity).
-- =====================================================================

-- DECLARE OR REPLACE VARIABLE as_of DATE DEFAULT DATE'2026-03-16';

-- ---------------------------------------------------------------------
-- 1) Edges valid at the as-of date (single version per element)
-- ---------------------------------------------------------------------
CREATE OR REPLACE TEMP VIEW edges AS
SELECT source_node_id, target_node_id, edge_type
FROM silver.network_edges
WHERE VALID_FROM <= as_of
  AND (VALID_TO > as_of OR VALID_TO IS NULL);

-- ---------------------------------------------------------------------
-- 2) Recursive region walk: a new region starts at each transformer's
--    downstream node; otherwise inherit the parent's region.
--    region_root = node where the region begins (source or transformer).
-- ---------------------------------------------------------------------
CREATE OR REPLACE TEMP VIEW voltage_regions AS
WITH RECURSIVE walk AS (
    -- anchor: source-rooted edges (parent = ROOT) start the top region
    SELECT e.target_node_id AS node,
           e.source_node_id AS parent,
           e.edge_type,
           e.target_node_id AS region_root,
           'source'         AS region_kind
    FROM edges e
    WHERE e.source_node_id = 'ROOT'

    UNION ALL

    SELECT c.target_node_id,
           c.source_node_id,
           c.edge_type,
           CASE WHEN c.edge_type = 'step_transformer'
                THEN c.target_node_id ELSE w.region_root END,
           CASE WHEN c.edge_type = 'step_transformer'
                THEN 'transformer' ELSE w.region_kind END
    FROM edges c
    JOIN walk w ON c.source_node_id = w.node
)
SELECT node, parent, edge_type, region_root, region_kind FROM walk;

-- ---------------------------------------------------------------------
-- 3) Map each region_root to its voltage:
--    source region   -> substation nominal voltage
--    transformer region -> transformer load-side (secondary) kV
-- ---------------------------------------------------------------------
CREATE OR REPLACE TEMP VIEW region_voltage AS
SELECT r.region_root,
       r.region_kind,
       CASE
         WHEN r.region_kind = 'source'      THEN s.nominal_voltage
         WHEN r.region_kind = 'transformer' THEN t.rated_voltage_loadside
       END AS region_kv
FROM (SELECT DISTINCT region_root, region_kind FROM voltage_regions) r
LEFT JOIN silver.network_substations s ON r.region_root = s.node_id
LEFT JOIN silver.network_transformers t ON r.region_root = t.node_id;

-- ---------------------------------------------------------------------
-- 4) FINAL: every node -> region + voltage  (this is what you pull)
-- ---------------------------------------------------------------------
CREATE OR REPLACE TEMP VIEW node_voltage AS
SELECT v.node, v.edge_type, v.region_root, rv.region_kind, rv.region_kv
FROM voltage_regions v
JOIN region_voltage rv ON v.region_root = rv.region_root;

-- ---- inspect: distinct regions and their voltages ----
SELECT region_kind, region_kv,
       COUNT(*) AS n_nodes, COUNT(DISTINCT region_root) AS n_regions
FROM node_voltage
GROUP BY region_kind, region_kv
ORDER BY region_kv DESC;

-- ---- QA: nodes that failed to get a voltage (transformer/source missing
--          its voltage row, or orphaned region) ----
-- SELECT * FROM node_voltage WHERE region_kv IS NULL;
