-- One flat MultiPolygon-per-measure table for OGC API - Features, derived
-- from convert-sql's own tables: the surface child rows collected back
-- into one MultiPolygon, each catalogue reference resolved to the
-- catalogue item's own TypeID/CoordID (what the DrawingRules' WHERE
-- compares). Only measures with a surface: the only shape this demo's
-- signature covers.
DROP TABLE IF EXISTS suel_planningmeasure_surface CASCADE;
CREATE TABLE suel_planningmeasure_surface AS
SELECT
    m.id,
    ST_Multi(ST_Collect(s.surface))::geometry(MultiPolygon, 2056) AS geom,
    t.typeid AS measure_type,
    c.coordid AS coordination_level
FROM {schema}.{measure} m
JOIN {schema}.{measure}_surface_surfaces s ON s.{measure}_fk = m.id
JOIN {schema}.measuretype t ON t.id = m.measuretype_reference
JOIN {schema}.coordinationlevel c ON c.id = m.coordinationlevel_reference
GROUP BY m.id, t.typeid, c.coordid;
ALTER TABLE suel_planningmeasure_surface ADD PRIMARY KEY (id);

-- OGC API - Maps convenience view: aliases the flat columns to the exact
-- dotted property paths interlis convert-sld emits for a WHERE clause
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
