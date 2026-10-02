-- OGC API - Maps convenience view: aliases the flat loader columns to the
-- exact dotted property paths interlis convert-sld emits for a WHERE clause
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
