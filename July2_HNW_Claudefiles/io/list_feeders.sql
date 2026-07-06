-- list_feeders.sql — the feeder-head reclosers (is_feeder) with element counts
-- PARAMETERS: :snapshot
SELECT
    p.element_name AS feeder_id,
    COUNT(DISTINCT p2.element_name) AS n_elements
FROM silver.usage_point_paths p
LEFT JOIN silver.usage_point_paths p2
    ON p2._snapshot_folder = :snapshot
   AND p2.path LIKE CONCAT('%', p.element_name, '%')
WHERE p._snapshot_folder = :snapshot
  AND p.is_feeder = true
GROUP BY p.element_name
ORDER BY p.element_name
;
