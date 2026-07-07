-- feeder_transformers.sql — transformer attributes for one feeder, valid at :as_of.
-- Phasing (has_phase_a/b/c) comes from network_transformers itself.
-- PARAMETERS: :as_of, :feeder_id
SELECT t.node_id,
       t.rated_voltage_srcside, t.rated_voltage_loadside,
       t.capacity_kva_a, t.capacity_kva_b, t.capacity_kva_c,
       t.has_phase_a, t.has_phase_b, t.has_phase_c
FROM {catalog}.silver.network_transformers t
WHERE t.VALID_FROM <= :as_of AND (t.VALID_TO > :as_of OR t.VALID_TO IS NULL)
  AND t.node_id IN (
      SELECT DISTINCT element_name FROM {catalog}.silver.usage_point_paths
      WHERE path LIKE CONCAT('%', :feeder_id, '%')
        AND VALID_FROM <= :as_of AND (VALID_TO > :as_of OR VALID_TO IS NULL)
  )
;
