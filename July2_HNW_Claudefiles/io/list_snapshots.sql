-- list_snapshots.sql — distinct validity dates (VALID_FROM) available.
SELECT DISTINCT VALID_FROM AS as_of
FROM {catalog}.silver.usage_point_paths
ORDER BY as_of
;
