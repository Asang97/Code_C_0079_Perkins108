-- feeder_source.sql — the substation (slack) this feeder traces to
-- PARAMETERS: :snapshot, :feeder_id
SELECT s.node_id, s.nominal_voltage, s.voltage_bus_ratio,
       s.has_phase_a, s.has_phase_b, s.has_phase_c
FROM silver.network_substations s
WHERE s._snapshot_folder = :snapshot
  AND s.node_id IN (
      SELECT DISTINCT element_name FROM silver.usage_point_paths
      WHERE _snapshot_folder = :snapshot AND path LIKE CONCAT('%', :feeder_id, '%')
        AND is_substation = true
  )
;
