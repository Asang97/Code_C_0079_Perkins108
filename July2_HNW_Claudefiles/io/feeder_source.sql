-- feeder_source.sql — the substation (slack) attributes, by its node id.
-- PARAMETERS: :as_of, :substation_id
SELECT s.node_id, s.nominal_voltage, s.voltage_bus_ratio,
       s.has_phase_a, s.has_phase_b, s.has_phase_c
FROM {catalog}.silver.network_substations s
WHERE s.VALID_FROM <= :as_of AND (s.VALID_TO > :as_of OR s.VALID_TO IS NULL)
  AND s.node_id = :substation_id
;
