-- list_feeders.sql — feeders (reclosers) directly below one substation.
-- Reverse tree: PREV_NODE_ID is the CHILD (toward loads). Children of the
-- substation node are its feeders. Cheap filter, no self-join.
-- PARAMETERS: :as_of, :substation_id
SELECT DISTINCT p.PREV_NODE_ID AS feeder_id
FROM {catalog}.silver.usage_point_paths p
WHERE p.CURRENT_NODE_ID = :substation_id
  AND p.PREV_NODE_ID IS NOT NULL
  AND p.VALID_FROM <= :as_of AND (p.VALID_TO > :as_of OR p.VALID_TO IS NULL)
ORDER BY feeder_id
;
