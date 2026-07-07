-- list_feeders.sql — feeder-head reclosers (is_feeder) valid at :as_of.
-- PARAMETERS: :as_of
SELECT
    p.element_name AS feeder_id,
    COUNT(DISTINCT p2.element_name) AS n_elements
FROM {catalog}.silver.usage_point_paths p
LEFT JOIN {catalog}.silver.usage_point_paths p2
    ON p2.path LIKE CONCAT('%', p.element_name, '%')
   AND p2.VALID_FROM <= :as_of AND (p2.VALID_TO > :as_of OR p2.VALID_TO IS NULL)
WHERE p.is_feeder = true
  AND p.VALID_FROM <= :as_of AND (p.VALID_TO > :as_of OR p.VALID_TO IS NULL)
GROUP BY p.element_name
ORDER BY p.element_name
;
