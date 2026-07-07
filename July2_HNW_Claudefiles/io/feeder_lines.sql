-- feeder_lines.sql — line attributes for one feeder's nodes, valid at :as_of.
-- PARAMETERS: :as_of, :feeder_id
SELECT l.node_id, l.line_type,
       l.conductor_eqdb_label_a, l.conductor_eqdb_label_b,
       l.conductor_eqdb_label_c, l.conductor_eqdb_label_neutral,
       l.impedance_length_ft, l.neutral_impedance_length_ft
FROM {catalog}.silver.network_lines l
WHERE l.VALID_FROM <= :as_of AND (l.VALID_TO > :as_of OR l.VALID_TO IS NULL)
  AND l.node_id IN (
      SELECT DISTINCT element_name FROM {catalog}.silver.usage_point_paths
      WHERE path LIKE CONCAT('%', :feeder_id, '%')
        AND VALID_FROM <= :as_of AND (VALID_TO > :as_of OR VALID_TO IS NULL)
  )
;
