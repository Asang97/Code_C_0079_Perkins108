-- ============================================================================
-- meter_loads.sql
-- ----------------------------------------------------------------------------
-- Turns AMI meter data into a structured per-consumer load table.
--
-- Does as much as possible in SQL so the Python layer receives one clean, wide
-- row per consumer node, carrying:
--   * demand totals (kW / kVAR) for each scenario (coincident, max) + kWh
--   * per-phase RMS voltage & current, so Python can weight the per-phase
--     split by apparent power (V*I)
--
-- Join chain (from the mapped schema):
--   grid_location.METER_NUMBER      = netsense_reading.DEVICE_NAME    (meter -> node)
--   netsense_reading.READING_TYPE_ID = readingdefinition.OBJECT_NUMBER (decode reading)
--   grid_location.USAGE_POINT       = the consumer node_id
--   grid_location.USAGE_POINT_PHASE = phasing (readings themselves are NOT
--                                     phase-labeled; phase comes from here)
--
-- PARAMETERS:
--   :snapshot   -- snapshot folder to scope the network side (if applicable)
--
-- ADJUST BEFORE USE:
--   * The TYPE / SUBTYPE / UOM string literals must match your
--     readingdefinition vocabulary exactly (e.g. 'CoincidentDemand', 'kW').
--   * The per-phase V/I discriminator (the `phase LIKE '%A%'` parts): phase is
--     NOT in the reading data, so confirm how per-phase V/I readings are
--     distinguished (a channel/register field, or distinct OBJECT_NUMBERs) and
--     replace the discriminator accordingly.
-- ============================================================================

WITH decoded AS (
    SELECT
        gl.USAGE_POINT              AS node_id,
        gl.USAGE_POINT_PHASE        AS phase,
        gl.METER_NUMBER             AS meter,
        rd.UOM,
        rd.TYPE,
        rd.SUBTYPE,
        r.READING_VALUE             AS val
    FROM semantic.grid_location gl
    JOIN bronze.netsense_reading r
        ON r.DEVICE_NAME = gl.METER_NUMBER
    JOIN silver.netsense_readingdefinition rd
        ON rd.OBJECT_NUMBER = r.READING_TYPE_ID
    WHERE gl.USAGE_POINT IS NOT NULL
)

SELECT
    node_id,
    MAX(phase) AS usage_point_phase,
    MAX(meter) AS meter,

    -- ---- demand totals (kW) per scenario -------------------------------------
    MAX(CASE WHEN UOM = 'kW'   AND SUBTYPE = 'CoincidentDemand' THEN val END) AS kw_coincident,
    MAX(CASE WHEN UOM = 'kW'   AND SUBTYPE = 'MaxDemand'        THEN val END) AS kw_max,

    -- kWh consumption -> Python derives average kW (needs period hours)
    MAX(CASE WHEN UOM = 'kWh'  AND TYPE = 'Consumption'         THEN val END) AS kwh_consumption,

    -- ---- reactive (kVAR) per scenario ----------------------------------------
    MAX(CASE WHEN UOM = 'kVAR' AND SUBTYPE = 'CoincidentDemand' THEN val END) AS kvar_coincident,
    MAX(CASE WHEN UOM = 'kVAR' AND SUBTYPE = 'MaxDemand'        THEN val END) AS kvar_max,
    MAX(CASE WHEN UOM = 'kVARh'                                 THEN val END) AS kvarh,

    -- ---- per-phase RMS voltage (average) for the V*I split -------------------
    MAX(CASE WHEN UOM = 'V' AND TYPE = 'RMS' AND SUBTYPE = 'Average' AND phase LIKE '%A%' THEN val END) AS v_a,
    MAX(CASE WHEN UOM = 'V' AND TYPE = 'RMS' AND SUBTYPE = 'Average' AND phase LIKE '%B%' THEN val END) AS v_b,
    MAX(CASE WHEN UOM = 'V' AND TYPE = 'RMS' AND SUBTYPE = 'Average' AND phase LIKE '%C%' THEN val END) AS v_c,

    -- ---- per-phase RMS current (average) for the V*I split -------------------
    MAX(CASE WHEN UOM = 'A' AND TYPE = 'RMS' AND SUBTYPE = 'Average' AND phase LIKE '%A%' THEN val END) AS i_a,
    MAX(CASE WHEN UOM = 'A' AND TYPE = 'RMS' AND SUBTYPE = 'Average' AND phase LIKE '%B%' THEN val END) AS i_b,
    MAX(CASE WHEN UOM = 'A' AND TYPE = 'RMS' AND SUBTYPE = 'Average' AND phase LIKE '%C%' THEN val END) AS i_c

FROM decoded
GROUP BY node_id
;