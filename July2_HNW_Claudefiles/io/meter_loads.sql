-- ============================================================================
-- meter_loads.sql  — AMI meter data -> per-consumer load table
-- ----------------------------------------------------------------------------
-- Join chain (bronze/silver only; no semantic schema):
--   silver.network_consumers.node_id      -> the consumer node + has_phase_a/b/c
--   silver.netsense_device.SITE_LOCATION  = node_id            (meter <-> node)
--   silver.netsense_device.DEVICE_NAME    = bronze.netsense_reading.DEVICE_NAME
--   bronze.netsense_reading.READING_TYPE_ID = silver.netsense_readingdefinition.OBJECT_NUMBER
--
-- Returns one wide row per consumer node: phasing + demand totals per scenario
-- + per-phase RMS V/I (avg) for the V*I split done in Python.
--
-- PARAMETERS:  :snapshot   (scopes the network-consumer side)
-- ADJUST: the UOM/TYPE/SUBTYPE string literals to your readingdefinition values.
-- ============================================================================
WITH decoded AS (
    SELECT
        nc.node_id                  AS node_id,
        nc.has_phase_a, nc.has_phase_b, nc.has_phase_c,
        dev.DEVICE_NAME             AS meter,
        rd.UOM, rd.TYPE, rd.SUBTYPE,
        r.READING_VALUE             AS val
    FROM silver.network_consumers nc
    JOIN silver.netsense_device dev
        ON dev.SITE_LOCATION = nc.node_id
    JOIN bronze.netsense_reading r
        ON r.DEVICE_NAME = dev.DEVICE_NAME
    JOIN silver.netsense_readingdefinition rd
        ON rd.OBJECT_NUMBER = r.READING_TYPE_ID
    WHERE nc._snapshot_folder = :snapshot
)
SELECT
    node_id,
    MAX(has_phase_a) AS has_phase_a,
    MAX(has_phase_b) AS has_phase_b,
    MAX(has_phase_c) AS has_phase_c,
    MAX(meter)       AS meter,

    -- demand totals (kW) per scenario
    MAX(CASE WHEN UOM='kW'   AND SUBTYPE='CoincidentDemand' THEN val END) AS kw_coincident,
    MAX(CASE WHEN UOM='kW'   AND SUBTYPE='MaxDemand'        THEN val END) AS kw_max,
    MAX(CASE WHEN UOM='kWh'  AND TYPE='Consumption'         THEN val END) AS kwh_consumption,

    -- reactive (kVAR)
    MAX(CASE WHEN UOM='kVAR' AND SUBTYPE='CoincidentDemand' THEN val END) AS kvar_coincident,
    MAX(CASE WHEN UOM='kVAR' AND SUBTYPE='MaxDemand'        THEN val END) AS kvar_max,
    MAX(CASE WHEN UOM='kVARh'                               THEN val END) AS kvarh,

    -- per-phase RMS voltage (average)
    MAX(CASE WHEN UOM='V' AND SUBTYPE='Average' AND TYPE LIKE '%A%' THEN val END) AS v_a,
    MAX(CASE WHEN UOM='V' AND SUBTYPE='Average' AND TYPE LIKE '%B%' THEN val END) AS v_b,
    MAX(CASE WHEN UOM='V' AND SUBTYPE='Average' AND TYPE LIKE '%C%' THEN val END) AS v_c,

    -- per-phase RMS current (average)
    MAX(CASE WHEN UOM='A' AND SUBTYPE='Average' AND TYPE LIKE '%A%' THEN val END) AS i_a,
    MAX(CASE WHEN UOM='A' AND SUBTYPE='Average' AND TYPE LIKE '%B%' THEN val END) AS i_b,
    MAX(CASE WHEN UOM='A' AND SUBTYPE='Average' AND TYPE LIKE '%C%' THEN val END) AS i_c
FROM decoded
GROUP BY node_id
;
