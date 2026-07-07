-- list_feeders.sql — the feeders (reclosers) directly below one substation.
-- In the reverse tree, PRE_NODE_ID is the CHILD (one step toward loads). So the
-- children of the substation node are its feeders. Cheap: filter, no self-join.
-- PARAMETERS: :as_of, :substation_id
SELECT DISTINCT p.pre_node_id AS feeder_id
FROM {catalog}.silver.usage_point_paths p
WHERE p.current_node_id = :substation_id
  AND p.pre_node_id IS NOT NULL
  AND p.VALID_FROM <= :as_of AND (p.VALID_TO > :as_of OR p.VALID_TO IS NULL)
ORDER BY feeder_id
;
