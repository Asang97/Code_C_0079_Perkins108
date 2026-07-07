-- feeder_elements.sql — all elements of ONE feeder, by walking DOWN the tree.
-- ----------------------------------------------------------------------------
-- The reverse tree: PRE_NODE_ID is the CHILD (toward loads). Starting from the
-- feeder node, we recursively follow CURRENT_NODE_ID -> PRE_NODE_ID to collect
-- every node downstream of the feeder. This replaces the expensive
-- `path LIKE '%feeder%'` self-join (which OOM'd) with a bounded tree walk that
-- only touches this feeder's subtree.
--
-- PARAMETERS: :as_of, :feeder_id
-- ----------------------------------------------------------------------------
WITH RECURSIVE
-- the validity-scoped edge set (parent = current, child = pre_node_id)
edges AS (
    SELECT current_node_id, pre_node_id, element_name,
           edge_type, node_type,
           has_phase_a, has_phase_b, has_phase_c, depth,
           is_transformer, is_substation, is_feeder,
           is_regulator, is_recloser, is_fuse
    FROM {catalog}.silver.usage_point_paths
    WHERE VALID_FROM <= :as_of AND (VALID_TO > :as_of OR VALID_TO IS NULL)
),
-- walk down from the feeder: seed = the feeder node, then follow to children
subtree AS (
    -- anchor: the feeder node itself
    SELECT current_node_id, pre_node_id, element_name, edge_type, node_type,
           has_phase_a, has_phase_b, has_phase_c, depth,
           is_transformer, is_substation, is_feeder,
           is_regulator, is_recloser, is_fuse
    FROM edges
    WHERE current_node_id = :feeder_id

    UNION ALL

    -- recurse: children (pre_node_id of the current frontier)
    SELECT e.current_node_id, e.pre_node_id, e.element_name, e.edge_type, e.node_type,
           e.has_phase_a, e.has_phase_b, e.has_phase_c, e.depth,
           e.is_transformer, e.is_substation, e.is_feeder,
           e.is_regulator, e.is_recloser, e.is_fuse
    FROM edges e
    JOIN subtree s ON e.current_node_id = s.pre_node_id
)
SELECT DISTINCT
    element_name, current_node_id, pre_node_id, edge_type, node_type,
    has_phase_a, has_phase_b, has_phase_c, depth,
    is_transformer, is_substation, is_feeder,
    is_regulator, is_recloser, is_fuse
FROM subtree
;
