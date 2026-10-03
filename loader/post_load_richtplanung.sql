-- Convenience view for pygeoapi: one feature per Flaeche, its MultiSurface
-- geometry already a single MultiPolygon column in convert-sql's schema.
CREATE OR REPLACE VIEW flaeche_geo AS
SELECT
    id,
    objektbezeichnung,
    beschrieb,
    objektart,
    genehmigungsdatum,
    beschlussdatumkanton,
    kanton,
    weblink,
    geometrie AS geom
FROM flaeche;

-- OGC API - Maps view: exposes objektart under the exact property name
-- interlis convert-sld emits for Flaeche_Graphics' WHERE clauses, so
-- MapScript's OGR/PostGIS reader resolves the SLD's ogc:PropertyName.
CREATE OR REPLACE VIEW flaeche_map AS
SELECT id, objektart AS "Objektart", geom
FROM flaeche_geo;
