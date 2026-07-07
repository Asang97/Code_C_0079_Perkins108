-- feeder_lines.sql — line attributes for an explicit set of nodes.
-- The node list comes from feeder_elements (the tree walk), so NO join here.
-- PARAMETERS: :as_of, :nodes (list of node_ids)
SELECT l.node_id, l.line_type,
       l.conductor_eqdb_label_a, l.conductor_eqdb_label_b,
       l.conductor_eqdb_label_c, l.conductor_eqdb_label_neutral,
       l.impedance_length_ft, l.neutral_impedance_length_ft
FROM {catalog}.silver.network_lines l
WHERE l.VALID_FROM <= :as_of AND (l.VALID_TO > :as_of OR l.VALID_TO IS NULL)
  AND l.node_id IN (:nodes)
;
