-- feeder_transformers.sql — transformer attributes for one feeder's nodes
-- Phasing (has_phase_a/b/c) comes from network_transformers itself.
-- PARAMETERS: :snapshot, :feeder_id
SELECT t.node_id,
       t.rated_voltage_srcside, t.rated_voltage_loadside,
       t.capacity_kva_a, t.capacity_kva_b, t.capacity_kva_c,
       t.has_phase_a, t.has_phase_b, t.has_phase_c
FROM silver.network_transformers t
WHERE t._snapshot_folder = :snapshot
  AND t.node_id IN (
      SELECT DISTINCT element_name FROM silver.usage_point_paths
      WHERE _snapshot_folder = :snapshot AND path LIKE CONCAT('%', :feeder_id, '%')
  )
;
