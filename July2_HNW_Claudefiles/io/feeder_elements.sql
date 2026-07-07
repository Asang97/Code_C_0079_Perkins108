-- feeder_elements.sql — DISTINCT elements of ONE feeder, with metadata.
-- ----------------------------------------------------------------------------
-- Step 1: take each usage point's LONGEST path (max DEPTH) under this feeder --
--         avoids the redundant shorter-prefix rows (no new info in them).
-- Step 2: EXPLODE the path string into distinct node ids (membership).
-- Step 3: JOIN the small distinct node set back to the path table ONCE to get
--         each node's metadata (edge_type, phasing, type flags, parent).
--
-- No recursion; the only join is against the small distinct node list, so it
-- stays well within memory (unlike the earlier path-LIKE self-join).
--
-- PATH format: |n1|->|n2|->|...|->|substation|  (pipe-wrapped, '->' separated)
-- PARAMETERS: :as_of, :feeder_id
-- ----------------------------------------------------------------------------
WITH valid AS (
    SELECT USAGE_POINT_ID, DEPTH, PATH, CURRENT_NODE_ID, PREV_NODE_ID,
           ELEMENT_NAME, EDGE_TYPE, NODE_TYPE,
           HAS_PHASE_A, HAS_PHASE_B, HAS_PHASE_C, DEPTH AS d,
           IS_TRANSFORMER, IS_SUBSTATION, IS_FEEDER,
           IS_REGULATOR, IS_RECLOSER, IS_FUSE
    FROM {catalog}.silver.usage_point_paths
    WHERE VALID_FROM <= :as_of AND (VALID_TO > :as_of OR VALID_TO IS NULL)
),
under_feeder AS (
    SELECT USAGE_POINT_ID, DEPTH, PATH
    FROM valid
    WHERE PATH LIKE CONCAT('%|', :feeder_id, '|%')
),
longest AS (
    SELECT USAGE_POINT_ID, MAX(DEPTH) AS max_depth
    FROM under_feeder GROUP BY USAGE_POINT_ID
),
member_nodes AS (                                   -- distinct membership
    SELECT DISTINCT REPLACE(node_raw, '|', '') AS node_id
    FROM under_feeder u
    JOIN longest l ON u.USAGE_POINT_ID = l.USAGE_POINT_ID AND u.DEPTH = l.max_depth
    LATERAL VIEW EXPLODE(SPLIT(u.PATH, '->')) t AS node_raw
)
-- join the small node set back to the path table for metadata (one row per node)
SELECT
    v.CURRENT_NODE_ID AS element_name,
    v.CURRENT_NODE_ID, v.PREV_NODE_ID, v.EDGE_TYPE, v.NODE_TYPE,
    v.HAS_PHASE_A, v.HAS_PHASE_B, v.HAS_PHASE_C, v.d AS depth,
    v.IS_TRANSFORMER, v.IS_SUBSTATION, v.IS_FEEDER,
    v.IS_REGULATOR, v.IS_RECLOSER, v.IS_FUSE
FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY CURRENT_NODE_ID ORDER BY d DESC) AS rn
    FROM valid
) v
JOIN member_nodes m ON v.CURRENT_NODE_ID = m.node_id
WHERE v.rn = 1        -- one representative row per node
;
