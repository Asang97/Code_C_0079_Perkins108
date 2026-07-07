-- list_substations.sql — all substations valid at :as_of.
-- PARAMETERS: :as_of
SELECT DISTINCT p.CURRENT_NODE_ID AS substation_id
FROM {catalog}.silver.usage_point_paths p
WHERE p.NODE_TYPE = 'substation'
  AND p.VALID_FROM <= :as_of AND (p.VALID_TO > :as_of OR p.VALID_TO IS NULL)
ORDER BY substation_id
;
