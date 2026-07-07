-- feeder_source.sql — the substation (slack) this feeder traces to, valid at :as_of.
-- PARAMETERS: :as_of, :feeder_id
SELECT s.node_id, s.nominal_voltage, s.voltage_bus_ratio,
       s.has_phase_a, s.has_phase_b, s.has_phase_c
FROM {catalog}.silver.network_substations s
WHERE s.VALID_FROM <= :as_of AND (s.VALID_TO > :as_of OR s.VALID_TO IS NULL)
  AND s.node_id IN (
      SELECT DISTINCT element_name FROM {catalog}.silver.usage_point_paths
      WHERE path LIKE CONCAT('%', :feeder_id, '%')
        AND is_substation = true
        AND VALID_FROM <= :as_of AND (VALID_TO > :as_of OR VALID_TO IS NULL)
  )
;
