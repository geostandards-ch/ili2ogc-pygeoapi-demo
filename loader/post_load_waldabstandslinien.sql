-- Convenience view for pygeoapi: same SELECT as ili2ogc's own auto-generated
-- view_waldabstand_linie VIEW, plus the base table's own "id" (a VIEW never
-- carries OID - pygeoapi's PostgreSQL provider requires an id_field).
CREATE OR REPLACE VIEW waldabstand_geo AS
SELECT
    wl.id,
    wl.geometrie AS geom,
    wl.publiziertab,
    wl.publiziertbis,
    wl.rechtsstatus,
    wl.bemerkungen AS bemerkungen_linie,
    t.code,
    t.bezeichnung,
    t.abkuerzung,
    t.verbindlichkeit,
    t.bemerkungen AS bemerkungen_typ
FROM waldabstand_linie wl
JOIN typ t ON wl.wal = t.id;
