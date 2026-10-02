-- Convenience view for pygeoapi: one geometry per Flaeche, aggregated from the
-- normalized flaeche_geometrie_surfaces child table that ili2ogc's convert-sql
-- produces for a BAG OF Surface attribute (real MultiSurface -> MultiPolygon).
CREATE OR REPLACE VIEW flaeche_geo AS
SELECT
    f.id,
    f.objektbezeichnung,
    f.beschrieb,
    f.objektart,
    f.genehmigungsdatum,
    f.beschlussdatumkanton,
    f.kanton,
    f.weblink,
    ST_Multi(ST_Union(g.surface)) AS geom
FROM flaeche f
JOIN flaeche_geometrie_surfaces g ON g.flaeche_fk = f.id
GROUP BY f.id, f.objektbezeichnung, f.beschrieb, f.objektart, f.genehmigungsdatum,
         f.beschlussdatumkanton, f.kanton, f.weblink;

-- OGC API - Maps view: exposes objektart under the exact property name
-- interlis convert-sld emits for Flaeche_Graphics' WHERE clauses, so
-- MapScript's OGR/PostGIS reader resolves the SLD's ogc:PropertyName.
CREATE OR REPLACE VIEW flaeche_map AS
SELECT id, objektart AS "Objektart", geom
FROM flaeche_geo;
