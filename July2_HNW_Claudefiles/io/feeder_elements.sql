-- feeder_elements.sql — all elements of ONE feeder via a tree walk DOWN.
-- Reverse tree: PREV_NODE_ID is the CHILD. From the feeder node, recursively
-- follow CURRENT_NODE_ID -> PREV_NODE_ID to collect the feeder's subtree.
-- Replaces the OOM-causing `path LIKE` self-join.
-- PARAMETERS: :as_of, :feeder_id
WITH RECURSIVE
edges AS (
    SELECT CURRENT_NODE_ID, PREV_NODE_ID, ELEMENT_NAME,
           EDGE_TYPE, NODE_TYPE,
           HAS_PHASE_A, HAS_PHASE_B, HAS_PHASE_C, DEPTH,
           IS_TRANSFORMER, IS_SUBSTATION, IS_FEEDER,
           IS_REGULATOR, IS_RECLOSER, IS_FUSE
    FROM {catalog}.silver.usage_point_paths
    WHERE VALID_FROM <= :as_of AND (VALID_TO > :as_of OR VALID_TO IS NULL)
),
subtree AS (
    SELECT * FROM edges WHERE CURRENT_NODE_ID = :feeder_id
    UNION ALL
    SELECT e.* FROM edges e
    JOIN subtree s ON e.CURRENT_NODE_ID = s.PREV_NODE_ID
)
SELECT DISTINCT
    ELEMENT_NAME, CURRENT_NODE_ID, PREV_NODE_ID, EDGE_TYPE, NODE_TYPE,
    HAS_PHASE_A, HAS_PHASE_B, HAS_PHASE_C, DEPTH,
    IS_TRANSFORMER, IS_SUBSTATION, IS_FEEDER,
    IS_REGULATOR, IS_RECLOSER, IS_FUSE
FROM subtree
;
