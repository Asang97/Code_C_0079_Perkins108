-- feeder_elements.sql — distinct elements belonging to one feeder
-- (every element whose path passes through the feeder-head recloser)
-- PARAMETERS: :snapshot, :feeder_id
SELECT DISTINCT
    p.element_name, p.current_node_id, p.pre_node_id,
    p.edge_type, p.node_type,
    p.has_phase_a, p.has_phase_b, p.has_phase_c,
    p.depth,
    p.is_transformer, p.is_substation, p.is_feeder,
    p.is_regulator, p.is_recloser, p.is_fuse
FROM silver.usage_point_paths p
WHERE p._snapshot_folder = :snapshot
  AND p.path LIKE CONCAT('%', :feeder_id, '%')
;
