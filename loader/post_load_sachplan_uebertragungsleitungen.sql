-- OGC API - Maps convenience view: aliases the flat loader columns to the
-- exact dotted property paths interlis convert-sld emits for a WHERE clause
-- chained through a REFERENCE TO (EXTERNAL) catalogue attribute
-- (MeasureType -> Reference -> TypeID), so MapScript's OGR/PostGIS reader
-- resolves the real SLD's se:Filter/PropertyName against a real column.
DROP VIEW IF EXISTS suel_planningmeasure_geo;
CREATE VIEW suel_planningmeasure_geo AS
SELECT
    id,
    geom,
    measure_type AS "MeasureType.Reference.TypeID",
    coordination_level AS "CoordinationLevel.Reference.CoordID"
FROM suel_planningmeasure_surface;
