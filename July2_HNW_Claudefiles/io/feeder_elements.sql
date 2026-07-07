-- feeder_elements.sql — distinct elements of one feeder, valid at :as_of.
-- PARAMETERS: :as_of, :feeder_id
SELECT DISTINCT
    p.element_name, p.current_node_id, p.pre_node_id,
    p.edge_type, p.node_type,
    p.has_phase_a, p.has_phase_b, p.has_phase_c,
    p.depth,
    p.is_transformer, p.is_substation, p.is_feeder,
    p.is_regulator, p.is_recloser, p.is_fuse
FROM {catalog}.silver.usage_point_paths p
WHERE p.path LIKE CONCAT('%', :feeder_id, '%')
  AND p.VALID_FROM <= :as_of AND (p.VALID_TO > :as_of OR p.VALID_TO IS NULL)
;
