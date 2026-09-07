#!/usr/bin/env python3
"""Loader: build a PostGIS schema from derived INTERLIS VIEW models via ili2ogc,
load real cantonal geodata into them, and materialize each VIEW as a .xtf.

Runs once per `docker-compose up`. One function per model - each is a
distinct pipeline (different base classes, different JOIN shape), not a
shared abstraction over two data points.
"""

import json
import os
import subprocess
import urllib.request
import zipfile

REPO = "/models"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def load_richtplanung(cur) -> None:
    """`RichtplanungErneuerbareEnergien_V1_d_01` (Projection, real SH data).

    ili2ogc's `convert-jsonfg` hoists `GeometryCHLV95_V1.MultiSurface` to a
    JSON-FG top-level "place" MultiPolygon (fixed after this demo surfaced
    it as real corpus evidence - see data/NOTICE.md) - reads "place"
    directly and hands each ring set to PostGIS via `ST_GeomFromGeoJSON`,
    one row per Polygon.
    """
    model = f"{REPO}/RichtplanungErneuerbareEnergien_V1_d_01.ili"
    source_url = (
        "https://geodienste.ch/downloads/interlis/richtplanung_erneuerbare_energien/SH/"
        "RichtplanungErneuerbareEnergien_V1_SH.xtf"
    )
    xtf = "/tmp/richtplanung_source.xtf"
    schema_sql = "/tmp/richtplanung_schema.sql"
    data_jsonfg = "/tmp/richtplanung_data.jsonfg.json"

    print(f"Downloading real source .xtf from {source_url}", flush=True)
    urllib.request.urlretrieve(source_url, xtf)

    run(["interlis", "validate", xtf, "--model", model, "--repo", REPO])
    run(["interlis", "convert-sql", model, "--repo", REPO, "--dialect", "postgresql", "-o", schema_sql])
    run(["interlis", "convert-jsonfg", xtf, "--model", model, "--repo", REPO, "-o", data_jsonfg])
    run(
        [
            "interlis",
            "write-xtf",
            model,
            xtf,
            "--repo",
            REPO,
            "--merge-with-source",
            "-o",
            "/data/view_flaeche.materialized.xtf",
        ]
    )

    cur.execute(
        "DROP VIEW IF EXISTS flaeche_geo CASCADE;"
        "DROP VIEW IF EXISTS view_flaeche CASCADE;"
        "DROP TABLE IF EXISTS flaeche_geometrie_surfaces, flaeche, energieform CASCADE;"
    )
    with open(schema_sql) as f:
        cur.execute(f.read())

    # This transfer never carries the external Energieform catalogue basket
    # (see data/NOTICE.md) - the FK/NOT NULL convert-sql derives for it
    # can't be satisfied by this single-file demo.
    cur.execute("ALTER TABLE flaeche DROP CONSTRAINT fk_energieformref_energieform_reference")
    cur.execute("ALTER TABLE flaeche ALTER COLUMN energieform_reference DROP NOT NULL")

    with open(data_jsonfg) as f:
        fc = json.load(f)

    flaeche_rows = 0
    surface_rows = 0
    for feat in fc["features"]:
        if feat["featureType"] != "Flaeche":
            continue
        p = feat["properties"]
        cur.execute(
            """INSERT INTO flaeche (id, energieform_reference, objektbezeichnung, beschrieb,
                   objektart, genehmigungsdatum, beschlussdatumkanton, kanton, weblink, bemerkungen)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                feat["id"],
                p.get("Energieform"),
                p.get("Objektbezeichnung"),
                p.get("Beschrieb"),
                p.get("Objektart"),
                p.get("Genehmigungsdatum"),
                p.get("BeschlussdatumKanton"),
                p.get("Kanton"),
                p.get("Weblink"),
                p.get("Bemerkungen"),
            ),
        )
        flaeche_rows += 1
        place = feat.get("place") or {}
        polygons = place.get("coordinates", []) if place.get("type") == "MultiPolygon" else []
        for rings in polygons:
            surface_rows += 1
            polygon = {"type": "Polygon", "coordinates": rings}
            cur.execute(
                """INSERT INTO flaeche_geometrie_surfaces (id, flaeche_fk, surface)
                   VALUES (%s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 2056))""",
                (f"surface-{surface_rows}", feat["id"], json.dumps(polygon)),
            )

    with open("/loader/post_load_richtplanung.sql") as f:
        cur.execute(f.read())

    print(f"richtplanung: loaded {flaeche_rows} Flaeche rows, {surface_rows} surfaces.", flush=True)


def load_waldabstandslinien(cur) -> None:
    """`Waldabstandslinien_V1_2_d` (JOIN OF Waldabstand_Linie, Typ; real GL data).

    Unlike `RichtplanungErneuerbareEnergien_V1_d_01`'s Projection, this
    JOIN OF VIEW's own ATTRIBUTE block maps `Waldabstand_Linie.Geometrie`
    (a native LineType, not a STRUCTURE-wrapped MultiSurface) straight
    through - `convert-sql`'s `CREATE VIEW` already exposes a real
    `geometry(LineString, 2056)` column with no child-table split needed
    (see docs/verified-view-corpus.md and models/Waldabstandslinien_V1_2_d.ili).
    Real data has exactly 1 `Typ` shared by all 5 `Waldabstand_Linie` - the
    single FK target is hardcoded rather than resolved from an embedded
    association role (`object_to_feature` doesn't expose association
    roles as properties without a `symbol_table` in "embedded roles" mode).
    """
    model = f"{REPO}/Waldabstandslinien_V1_2_d.ili"
    source_url = "https://www.geodienste.ch/downloads/interlis/npl_waldabstandslinien/GL/ch_np_wal_v1_2.xtf"
    xtf = "/tmp/waldabstandslinien_source.xtf"
    schema_sql = "/tmp/waldabstandslinien_schema.sql"
    data_jsonfg = "/tmp/waldabstandslinien_data.jsonfg.json"

    print(f"Downloading real source .xtf from {source_url}", flush=True)
    urllib.request.urlretrieve(source_url, xtf)

    run(["interlis", "validate", xtf, "--model", model, "--repo", REPO])
    run(["interlis", "convert-sql", model, "--repo", REPO, "--dialect", "postgresql", "-o", schema_sql])
    run(["interlis", "convert-jsonfg", xtf, "--model", model, "--repo", REPO, "-o", data_jsonfg])
    run(
        [
            "interlis",
            "write-xtf",
            model,
            xtf,
            "--repo",
            REPO,
            "--merge-with-source",
            "-o",
            "/data/view_waldabstand_linie.materialized.xtf",
        ]
    )

    cur.execute(
        "DROP VIEW IF EXISTS waldabstand_geo CASCADE;"
        "DROP VIEW IF EXISTS view_waldabstand_linie CASCADE;"
        "DROP TABLE IF EXISTS waldabstand_linie, typ CASCADE;"
    )
    with open(schema_sql) as f:
        cur.execute(f.read())

    with open(data_jsonfg) as f:
        fc = json.load(f)

    typ_ids = []
    for feat in fc["features"]:
        if feat["featureType"] != "Typ":
            continue
        p = feat["properties"]
        cur.execute(
            """INSERT INTO typ (id, code, bezeichnung, abkuerzung, verbindlichkeit, bemerkungen)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (feat["id"], p.get("Code"), p.get("Bezeichnung"), p.get("Abkuerzung"), p.get("Verbindlichkeit"), p.get("Bemerkungen")),
        )
        typ_ids.append(feat["id"])
    sole_typ_id = typ_ids[0]

    linie_rows = 0
    for feat in fc["features"]:
        if feat["featureType"] != "Waldabstand_Linie":
            continue
        p = feat["properties"]
        place = feat.get("place") or {}
        cur.execute(
            """INSERT INTO waldabstand_linie (id, geometrie, publiziertab, publiziertbis, rechtsstatus,
                   bemerkungen, wal)
               VALUES (%s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 2056), %s, %s, %s, %s, %s)""",
            (
                feat["id"],
                json.dumps(place),
                p.get("publiziertAb"),
                p.get("publiziertBis"),
                p.get("Rechtsstatus"),
                p.get("Bemerkungen"),
                sole_typ_id,
            ),
        )
        linie_rows += 1

    with open("/loader/post_load_waldabstandslinien.sql") as f:
        cur.execute(f.read())

    print(f"waldabstandslinien: loaded {linie_rows} Waldabstand_Linie rows, {len(typ_ids)} Typ.", flush=True)


def load_mainroads(cur) -> None:
    """`MainRoads_LV95_V1_1_d` (Projection, real Swiss-wide data, 135 objects).

    Same shape as `RichtplanungErneuerbareEnergien_V1_d_01`: `view_roadsegment`
    doesn't map `RoadSegment.Geometry` (a Projection view, like model 1 -
    see data/NOTICE.md). Unlike model 1's `MultiSurface` though,
    `GeometryCHLV95_V1.LineWithAltitude` is a native `LineType` (3D
    POLYLINE) - `convert-sql` already puts a real `geometry(LineStringZ,
    2056)` column straight on the `roadsegment` table itself, no
    child-table split needed - pygeoapi is pointed at that table directly,
    no convenience view required for this one.

    Source is a ZIP (`data.zip`), unlike the other 2 models' bare `.xtf`.
    """
    model = f"{REPO}/MainRoads_LV95_V1_1_d.ili"
    source_url = "https://data.geo.admin.ch/ch.astra.hauptstrassennetz/hauptstrassennetz/hauptstrassennetz_2056.xtf.zip"
    zip_path = "/tmp/mainroads_source.zip"
    xtf = "/tmp/mainroads_source.xtf"
    schema_sql = "/tmp/mainroads_schema.sql"
    data_jsonfg = "/tmp/mainroads_data.jsonfg.json"

    print(f"Downloading real source .xtf from {source_url}", flush=True)
    urllib.request.urlretrieve(source_url, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        (xtf_member,) = [n for n in zf.namelist() if n.endswith(".xtf")]
        with zf.open(xtf_member) as src, open(xtf, "wb") as dst:
            dst.write(src.read())

    run(["interlis", "validate", xtf, "--model", model, "--repo", REPO])
    run(["interlis", "convert-sql", model, "--repo", REPO, "--dialect", "postgresql", "-o", schema_sql])
    run(["interlis", "convert-jsonfg", xtf, "--model", model, "--repo", REPO, "-o", data_jsonfg])
    run(
        [
            "interlis",
            "write-xtf",
            model,
            xtf,
            "--repo",
            REPO,
            "--merge-with-source",
            "-o",
            "/data/view_roadsegment.materialized.xtf",
        ]
    )

    cur.execute("DROP VIEW IF EXISTS view_roadsegment CASCADE; DROP TABLE IF EXISTS roadsegment CASCADE;")
    with open(schema_sql) as f:
        cur.execute(f.read())

    with open(data_jsonfg) as f:
        fc = json.load(f)

    rows = 0
    for feat in fc["features"]:
        if feat["featureType"] != "RoadSegment":
            continue
        p = feat["properties"]
        cur.execute(
            """INSERT INTO roadsegment (id, geometry, canton, roadnumber, segmentdescription)
               VALUES (%s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 2056), %s, %s, %s)""",
            (feat["id"], json.dumps(feat["place"]), p.get("Canton"), p.get("RoadNumber"), p.get("SegmentDescription")),
        )
        rows += 1

    print(f"mainroads: loaded {rows} RoadSegment rows.", flush=True)


def _place_to_wkt(place: dict) -> str:
    """A JSON-FG "place" geometry (LineString/CircularString/CompoundCurve, 2D) -> PostGIS WKT.

    `ST_GeomFromGeoJSON` can't take CircularString/CompoundCurve - JSON-FG
    Part 1 SS7.5 conformance classes ili2ogc's own circular-arcs support
    already needs, not part of plain GeoJSON/RFC 7946 - so this handles
    exactly the 3 shapes `convert-jsonfg` produces for a `POLYLINE WITH
    (STRAIGHTS, ARCS)` attribute, via `ST_GeomFromText` instead.
    """

    def coords(pts: list[list[float]]) -> str:
        return ", ".join(f"{x} {y}" for x, y in pts)

    kind = place["type"]
    if kind == "LineString":
        return f"LINESTRING({coords(place['coordinates'])})"
    if kind == "CircularString":
        return f"CIRCULARSTRING({coords(place['coordinates'])})"
    if kind == "CompoundCurve":
        parts = []
        for g in place["geometries"]:
            if g["type"] == "CircularString":
                parts.append(f"CIRCULARSTRING({coords(g['coordinates'])})")
            else:
                parts.append(f"({coords(g['coordinates'])})")
        return f"COMPOUNDCURVE({', '.join(parts)})"
    raise ValueError(f"unsupported place type for WKT: {kind!r}")


def load_buildinglinesformotorways(cur) -> None:
    """`BuildingLinesForMotorways_V2_2_d` (Projection, real ASTRA data, 1st corpus case with an ARC segment).

    Real source is 3686 objects (9.5 MB `.xtf`, ~50 MB once merged with
    `write-xtf --merge-with-source`) - too large for this demo repo, so
    `data/buildingline_sample_source.xtf` is a curated 30-object sample
    (15 straight `LineString`, 15 with at least one `ARC` segment -
    `CircularString`/`CompoundCurve` in JSON-FG), committed directly
    rather than downloaded (see data/NOTICE.md for the sampling method
    and the full real source URL).

    `convert-sql` types `buildingline.geometry` as `geometry(LineString,
    2056)` (the attribute's base VERTEX type) - too narrow for the
    `CircularString`/`CompoundCurve` rows real data actually has, so this
    loader widens it to a generic `geometry(Geometry, 2056)` after
    running the generated schema (real finding, not an ili2ogc bug - the
    column type reflects the attribute's declared INTERLIS type, which
    doesn't distinguish "may have ARCs" at that granularity).

    `pygeoapi`'s collection is served through `ST_CurveToLine(geometry)`
    (see `loader/post_load_buildinglinesformotorways.sql`) - GeoJSON
    (RFC 7946, what pygeoapi ultimately emits, JSON-FG formatter
    included) has no curve types at all, so the live map necessarily
    shows a linearized approximation; the true curve survives only in
    PostGIS itself and in `data/view_buildingline.jsonfg.json`.
    """
    model = f"{REPO}/BuildingLinesForMotorways_V2_2_d.ili"
    xtf = "/data/buildingline_sample_source.xtf"
    schema_sql = "/tmp/buildingline_schema.sql"
    data_jsonfg = "/tmp/buildingline_data.jsonfg.json"

    run(["interlis", "validate", xtf, "--model", model, "--repo", REPO])
    run(["interlis", "convert-sql", model, "--repo", REPO, "--dialect", "postgresql", "-o", schema_sql])
    run(["interlis", "convert-jsonfg", xtf, "--model", model, "--repo", REPO, "-o", data_jsonfg])
    run(
        [
            "interlis",
            "write-xtf",
            model,
            xtf,
            "--repo",
            REPO,
            "--merge-with-source",
            "-o",
            "/data/view_buildingline.materialized.xtf",
        ]
    )

    cur.execute(
        "DROP VIEW IF EXISTS buildingline_geo CASCADE;DROP VIEW IF EXISTS view_buildingline CASCADE;"
        "DROP TABLE IF EXISTS buildingline CASCADE;"
    )
    with open(schema_sql) as f:
        cur.execute(f.read())
    cur.execute("ALTER TABLE buildingline ALTER COLUMN geometry TYPE geometry(Geometry, 2056)")

    with open(data_jsonfg) as f:
        fc = json.load(f)

    rows = 0
    for feat in fc["features"]:
        if feat["featureType"] != "BuildingLine":
            continue
        p = feat["properties"]
        cur.execute(
            """INSERT INTO buildingline (id, geometry, status, approvaldate, approvingauthority,
                   planningapprovalname, publicationdatefrom, publicationdateto, weblink)
               VALUES (%s, ST_SetSRID(ST_GeomFromText(%s), 2056), %s, %s, %s, %s, %s, %s, %s)""",
            (
                feat["id"],
                _place_to_wkt(feat["place"]),
                p.get("Status"),
                p.get("ApprovalDate"),
                p.get("ApprovingAuthority"),
                p.get("PlanningApprovalName"),
                p.get("PublicationDateFrom"),
                p.get("PublicationDateTo"),
                p.get("WebLink"),
            ),
        )
        rows += 1

    with open("/loader/post_load_buildinglinesformotorways.sql") as f:
        cur.execute(f.read())

    print(f"buildinglinesformotorways: loaded {rows} BuildingLine rows.", flush=True)


def main() -> None:
    run(["pip", "install", "--no-cache-dir", "-q", "-e", "/interlis-runtime"])
    import psycopg2  # noqa: PLC0415 (installed above, import after pip install)

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    load_richtplanung(cur)
    load_waldabstandslinien(cur)
    load_mainroads(cur)
    load_buildinglinesformotorways(cur)
    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
