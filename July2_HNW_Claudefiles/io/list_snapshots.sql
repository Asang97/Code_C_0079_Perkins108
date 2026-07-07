-- list_snapshots.sql — distinct validity dates available in the network.
-- Silver uses VALID_FROM/VALID_TO (not a snapshot folder). This returns the
-- distinct VALID_FROM dates you can use as an :as_of point-in-time.
SELECT DISTINCT VALID_FROM AS as_of
FROM {catalog}.silver.usage_point_paths
ORDER BY as_of
;
