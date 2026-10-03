-- One flat point-per-facility table for OGC API - Features, derived from
-- convert-sql's own tables: the MultiPoint geometry, the German name, and
-- each catalogue reference resolved to the catalogue item's own
-- KindID/StatusID (what the DrawingRules' WHERE compares, not the raw REF TID).
DROP TABLE IF EXISTS spa_facility_point CASCADE;
CREATE TABLE spa_facility_point AS
SELECT
    f.id,
    f.point::geometry(MultiPoint, 2056) AS geom,
    (SELECT n.text FROM {schema}.{facility}_name_localisedtext n
     WHERE n.{facility}_fk = f.id AND n.language = 'de') AS name,
    k.kindid AS facility_kind,
    s.statusid AS facility_status
FROM {schema}.{facility} f
JOIN {schema}.facilitykind k ON k.id = f.facilitykind_reference
JOIN {schema}.facilitystatus s ON s.id = f.facilitystatus_reference
WHERE f.point IS NOT NULL;
ALTER TABLE spa_facility_point ADD PRIMARY KEY (id);

-- OGC API - Maps convenience view: aliases the flat columns to the exact
-- dotted property paths interlis convert-sld emits for a WHERE clause
-- chained through a REFERENCE TO (EXTERNAL) catalogue attribute
-- (FacilityKind -> Reference -> KindID), so MapScript's OGR/PostGIS reader
-- resolves the real SLD's se:Filter/PropertyName against a real column.
DROP VIEW IF EXISTS spa_facility_geo;
CREATE VIEW spa_facility_geo AS
SELECT
    id,
    geom,
    facility_kind AS "FacilityKind.Reference.KindID",
    facility_status AS "FacilityStatus.Reference.StatusID"
FROM spa_facility_point;
