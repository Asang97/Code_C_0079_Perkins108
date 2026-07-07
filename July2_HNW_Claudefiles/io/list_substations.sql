-- list_substations.sql — all substations valid at :as_of.
-- Cheap: a filter on NODE_TYPE, no join. Substation = the slack of its feeders.
-- PARAMETERS: :as_of
SELECT DISTINCT p.current_node_id AS substation_id
FROM {catalog}.silver.usage_point_paths p
WHERE p.node_type = 'substation'
  AND p.VALID_FROM <= :as_of AND (p.VALID_TO > :as_of OR p.VALID_TO IS NULL)
ORDER BY substation_id
;
