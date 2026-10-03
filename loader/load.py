#!/usr/bin/env python3
"""Loader: build a PostGIS schema from derived INTERLIS VIEW models via ili2ogc,
load real cantonal geodata into them, and materialize each VIEW as a .xtf.

Runs once per `docker-compose up`. One function per model - each is a
distinct pipeline (different base classes, different JOIN shape), not a
shared abstraction over two data points.
"""

import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

REPO = "/models"
SOURCE_XTF_DIR = "/data/source-xtf"
SYMBOLOGY_MODEL = f"{REPO}/DemoSymbology.ili"
SYMBOLOGY_XTF = "/data/symbology.xtf"
SUEL_SYMBOLOGY_MODEL = f"{REPO}/SachplanUebertragungsleitungen.ili"
SUEL_SYMBOLOGY_XTF = "/data/symbology_uebertragungsleitungen.xtf"
SPA_SYMBOLOGY_MODEL = f"{REPO}/SachplanAsyl.ili"
SPA_SYMBOLOGY_XTF = "/data/symbology_asyl.xtf"
_ILI24_NS = "http://www.interlis.ch/INTERLIS2.3"


def run(cmd: list[str], accept_degraded: bool = False) -> None:
    """Run an ili2ogc command; exit 2 (completed, notes/warnings only) passes only if `accept_degraded`."""
    print("+", " ".join(cmd), flush=True)
    returncode = subprocess.run(cmd).returncode
    if returncode not in ((0, 2) if accept_degraded else (0,)):
        raise subprocess.CalledProcessError(returncode, cmd)


def load_richtplanung(cur) -> None:
    """`RichtplanungErneuerbareEnergien_V1_d_01` (Projection, real SH data).

    ili2ogc's `convert-jsonfg` hoists `GeometryCHLV95_V1.MultiSurface` to a
    JSON-FG top-level "place" MultiPolygon (fixed after this demo surfaced
    it as real corpus evidence) - reads "place"
    directly and hands each ring set to PostGIS via `ST_GeomFromGeoJSON`,
    one row per Polygon.
    """
    model = f"{REPO}/RichtplanungErneuerbareEnergien_V1_d_01.ili"
    # Source: https://geodienste.ch/downloads/interlis/richtplanung_erneuerbare_energien/SH/RichtplanungErneuerbareEnergien_V1_SH.xtf
    xtf = "/tmp/richtplanung_source.xtf"
    schema_sql = "/tmp/richtplanung_schema.sql"
    data_jsonfg = "/tmp/richtplanung_data.jsonfg.json"

    shutil.copy(f"{SOURCE_XTF_DIR}/RichtplanungErneuerbareEnergien_V1_SH.xtf", xtf)

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
    # - the FK/NOT NULL convert-sql derives for it
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
    # Source: https://www.geodienste.ch/downloads/interlis/npl_waldabstandslinien/GL/ch_np_wal_v1_2.xtf
    xtf = "/tmp/waldabstandslinien_source.xtf"
    schema_sql = "/tmp/waldabstandslinien_schema.sql"
    data_jsonfg = "/tmp/waldabstandslinien_data.jsonfg.json"

    shutil.copy(f"{SOURCE_XTF_DIR}/ch_np_wal_v1_2.xtf", xtf)

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
    doesn't map `RoadSegment.Geometry` (a Projection view, like model 1).
    Unlike model 1's `MultiSurface` though,
    `GeometryCHLV95_V1.LineWithAltitude` is a native `LineType` (3D
    POLYLINE) - `convert-sql` already puts a real `geometry(LineStringZ,
    2056)` column straight on the `roadsegment` table itself, no
    child-table split needed - pygeoapi is pointed at that table directly,
    no convenience view required for this one.

    Source is a ZIP (`data.zip`), unlike the other 2 models' bare `.xtf`.
    """
    model = f"{REPO}/MainRoads_LV95_V1_1_d.ili"
    # Source: https://data.geo.admin.ch/ch.astra.hauptstrassennetz/hauptstrassennetz/hauptstrassennetz_2056.xtf.zip
    zip_path = f"{SOURCE_XTF_DIR}/hauptstrassennetz_2056.xtf.zip"
    xtf = "/tmp/mainroads_source.xtf"
    schema_sql = "/tmp/mainroads_schema.sql"
    data_jsonfg = "/tmp/mainroads_data.jsonfg.json"

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
    rather than downloaded (full source:
    https://data.geo.admin.ch/ch.astra.baulinien-nationalstrassen).

    `convert-sql` types `buildingline.geometry` as `geometry(LineString,
    2056)` (the attribute's base VERTEX type) - too narrow for the
    `CircularString`/`CompoundCurve` rows real data actually has, so this
    loader widens it to a generic `geometry(Geometry, 2056)` after
    running the generated schema (real finding, not an ili2ogc bug - the
    column type reflects the attribute's declared INTERLIS type, which
    doesn't distinguish "may have ARCs" at that granularity).

    `pygeoapi`'s collection is served through `ST_CurveToLine(geometry)`
    (see `loader/post_load_buildinglinesformotorways.sql`) - GeoJSON
    (RFC 7946, what pygeoapi ultimately emits) has no curve types at all,
    so the live map necessarily shows a linearized approximation; the
    true curve survives only in PostGIS itself.
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


def _merge_ili24_baskets(main_path: str, extra_paths: list[str], out_path: str) -> None:
    """Merge extra `.xtf`/catalogue `.xml` transfers into `main_path`'s own `DATASECTION`.

    `REFERENCE TO (EXTERNAL)` only resolves within objects present in the
    SAME parsed transfer, so the main dataset and its 3 separate catalogue
    files need combining before `interlis convert-jsonfg`.
    """
    ET.register_namespace("", _ILI24_NS)
    main_tree = ET.parse(main_path)
    main_data = main_tree.getroot().find(f"{{{_ILI24_NS}}}DATASECTION")
    main_basket = next(iter(main_data))

    for extra_path in extra_paths:
        extra_data = ET.parse(extra_path).getroot().find(f"{{{_ILI24_NS}}}DATASECTION")
        for extra_basket in list(extra_data):
            if extra_basket.tag == main_basket.tag and extra_basket.get("BID") == main_basket.get("BID"):
                for child in list(extra_basket):
                    main_basket.append(child)
            else:
                main_data.append(extra_basket)

    main_tree.write(out_path, encoding="UTF-8", xml_declaration=True)


# (feature type, table, catalogue id column, JSON-FG property) - the base
# model's catalogues, shared by both Sachplan collections.
_SECTORAL_PLAN_CATALOGUES = [
    ("FacilityKind", "facilitykind", "kindid", "KindID"),
    ("FacilityStatus", "facilitystatus", "statusid", "StatusID"),
    ("MeasureType", "measuretype", "typeid", "TypeID"),
    ("CoordinationLevel", "coordinationlevel", "coordid", "CoordID"),
    ("PlanningStatus", "planningstatus", "statusid", "StatusID"),
]


def _lv95_table(cur, schema: str, base: str) -> str:
    """Return `base` or its `_2` twin, whichever holds LV95 geometry.

    The base model file declares an LV03 and an LV95 variant with the same
    class names; convert-sql suffixes the second one it meets, so the
    suffix alone doesn't say which variant a table belongs to.
    """
    cur.execute(
        "SELECT f_table_name FROM geometry_columns WHERE srid = 2056 AND f_table_schema = %s AND f_table_name IN (%s, %s)",
        (schema, f"{base}_point_points", f"{base}_2_point_points"),
    )
    return cur.fetchone()[0].removesuffix("_point_points")


def _mod_info(p: dict) -> tuple:
    mod_info = p.get("ModInfo") or {}
    return mod_info.get("ValidFrom"), mod_info.get("ValidUntil"), mod_info.get("LatestModification")


def _load_sectoral_plan(cur, schema: str, model: str, merged_xtf: str) -> dict[str, str]:
    """Load a `BaseModel_SectoralPlans_V1_4` transfer into its convert-sql schema, in its own PostgreSQL schema.

    Both Sachplan collections share the base model, so their tables have the
    same names - one PostgreSQL schema each keeps them apart. Returns the
    LV95 table names, for the post-load SQL.
    """
    schema_sql = f"/tmp/{schema}_schema.sql"
    data_jsonfg = f"/tmp/{schema}_data.jsonfg.json"
    run(["interlis", "validate", merged_xtf, "--model", model, "--repo", REPO])
    # The base model's `MANDATORY CONSTRAINT DEFINED(Point) OR ...` can't
    # become a CHECK (Point lives in a child table): a note, exit 2.
    run(
        ["interlis", "convert-sql", model, "--repo", REPO, "--dialect", "postgresql", "-o", schema_sql],
        accept_degraded=True,
    )
    run(["interlis", "convert-jsonfg", merged_xtf, "--model", model, "--repo", REPO, "-o", data_jsonfg])

    cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE; CREATE SCHEMA {schema}; SET search_path TO {schema}, public;")
    with open(schema_sql) as f:
        cur.execute(f.read())
    facility = _lv95_table(cur, schema, "facility")
    measure = _lv95_table(cur, schema, "planningmeasure")

    with open(data_jsonfg) as f:
        features = json.load(f)["features"]

    for feature_type, table, id_column, prop in _SECTORAL_PLAN_CATALOGUES:
        for feat in features:
            if feat["featureType"] == feature_type:
                cur.execute(
                    f"INSERT INTO {table} (id, {id_column}) VALUES (%s, %s)", (feat["id"], feat["properties"][prop])
                )

    for feat in features:
        p = feat["properties"]
        if feat["featureType"] == "Facility":
            cur.execute(
                f"""INSERT INTO {facility} (id, facilitykind_reference, facilitystatus_reference, symbolori,
                       modinfo_validfrom, modinfo_validuntil, modinfo_latestmodification)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (feat["id"], p["FacilityKind"], p["FacilityStatus"], p.get("SymbolOri"), *_mod_info(p)),
            )
            # Facility.Point is the base model's own MultiPoint STRUCTURE,
            # not a standard geometry type, so it stays in properties.
            for n, item in enumerate((p.get("Point") or {}).get("Points") or []):
                cur.execute(
                    f"""INSERT INTO {facility}_point_points (id, {facility}_fk, point)
                        VALUES (%s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 2056))""",
                    (f"{feat['id']}-p{n}", feat["id"], json.dumps(item["Point"])),
                )
            for n, text in enumerate((p.get("Name") or {}).get("LocalisedText") or []):
                cur.execute(
                    f"""INSERT INTO {facility}_name_localisedtext (id, {facility}_fk, language, text)
                        VALUES (%s, %s, %s, %s)""",
                    (f"{feat['id']}-n{n}", feat["id"], text.get("Language"), text["Text"]),
                )
        elif feat["featureType"] == "PlanningMeasure":
            cur.execute(
                f"""INSERT INTO {measure} (id, measuretype_reference, coordinationlevel_reference,
                       planningstatus_reference, symbolori, modinfo_validfrom, modinfo_validuntil,
                       modinfo_latestmodification)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    feat["id"],
                    p["MeasureType"],
                    p["CoordinationLevel"],
                    p["PlanningStatus"],
                    p.get("SymbolOri"),
                    *_mod_info(p),
                ),
            )
            place = feat.get("place") or {}
            polygons = {"Polygon": [place.get("coordinates")], "MultiPolygon": place.get("coordinates")}.get(
                place.get("type"), []
            )
            for n, rings in enumerate(polygons):
                cur.execute(
                    f"""INSERT INTO {measure}_surface_surfaces (id, {measure}_fk, surface)
                        VALUES (%s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 2056))""",
                    (f"{feat['id']}-s{n}", feat["id"], json.dumps({"type": "Polygon", "coordinates": rings})),
                )

    cur.execute("SET search_path TO public;")
    return {"schema": schema, "facility": facility, "measure": measure}


def load_sachplan_uebertragungsleitungen(cur) -> None:
    """`TransmissionLinesSectoralPlan_V1_4` (Sachplan Übertragungsleitungen, real BFE data).

    `Facility`/`PlanningMeasure` live on the shared
    `BaseModel_SectoralPlans_LV95_V1_4`, folded into convert-sql's schema
    through the topic extension.
    """
    model = f"{REPO}/TransmissionLinesSectoralPlan_V1_4.ili"
    zip_path = f"{SOURCE_XTF_DIR}/sachplan-uebertragungsleitungen_kraft_2056.xtf.zip"
    main_xtf = "/tmp/suel_main.xtf"
    mt_catalogue = "/tmp/suel_measuretype_catalogue.xml"
    fk_catalogue = "/tmp/suel_facilitykind_catalogue.xml"
    shared_catalogue = "/tmp/suel_shared_catalogue.xml"
    merged_xtf = "/data/sachplan_uebertragungsleitungen.merged.xtf"

    # Source: https://data.geo.admin.ch/ch.bfe.sachplan-uebertragungsleitungen_kraft/
    # sachplan-uebertragungsleitungen_kraft/sachplan-uebertragungsleitungen_kraft_2056.xtf.zip
    with zipfile.ZipFile(zip_path) as zf:
        names = {n.rsplit("/", 1)[-1]: n for n in zf.namelist()}
        with zf.open(names["TransmissionLinesSectoralPlan.xtf"]) as src, open(main_xtf, "wb") as dst:
            dst.write(src.read())
        with zf.open(next(n for n in zf.namelist() if "MeasureTypeCatalogue" in n)) as src, open(
            mt_catalogue, "wb"
        ) as dst:
            dst.write(src.read())
        with zf.open(next(n for n in zf.namelist() if "FacilityKindCatalogue" in n)) as src, open(
            fk_catalogue, "wb"
        ) as dst:
            dst.write(src.read())
        with zf.open(names["SectoralPlans_Catalogues_V1_4.xml"]) as src, open(shared_catalogue, "wb") as dst:
            dst.write(src.read())

    _merge_ili24_baskets(main_xtf, [mt_catalogue, fk_catalogue, shared_catalogue], merged_xtf)
    tables = _load_sectoral_plan(cur, "suel", model, merged_xtf)

    with open("/loader/post_load_sachplan_uebertragungsleitungen.sql") as f:
        cur.execute(f.read().format(**tables))
    cur.execute("SELECT count(*) FROM suel_planningmeasure_surface")
    print(f"sachplan_uebertragungsleitungen: loaded {cur.fetchone()[0]} PlanningMeasure surface rows.", flush=True)


def load_sachplan_asyl(cur) -> None:
    """`SectoralPlanForAsylum_LV95_V1_4` (Sachplan Asyl, real SEM data).

    The model only extends the base model's topic: every object is a bare
    base-model `Facility`/`PlanningMeasure`. The SEM catalogue
    (FacilityKind) is vendored next to the data; the cross-Sachplan
    catalogue (FacilityStatus) is the same file Übertragungsleitungen
    ships, read from its archive.
    """
    model = f"{REPO}/SectoralPlanForAsylum_V1_4.ili"
    main_xtf = "/tmp/spa_main.xtf"
    shared_catalogue = "/tmp/spa_shared_catalogue.xml"
    merged_xtf = "/data/sachplan_asyl.merged.xtf"

    # Source: https://data.geo.admin.ch/ch.sem.sachplan-asyl_kraft/sachplan-asyl_kraft/sachplan-asyl_kraft_2056.zip
    with zipfile.ZipFile(f"{SOURCE_XTF_DIR}/sachplan-asyl_kraft_2056.zip") as zf:
        with zf.open(next(n for n in zf.namelist() if n.endswith(".xtf"))) as src, open(main_xtf, "wb") as dst:
            dst.write(src.read())
    with zipfile.ZipFile(f"{SOURCE_XTF_DIR}/sachplan-uebertragungsleitungen_kraft_2056.xtf.zip") as zf:
        with zf.open(next(n for n in zf.namelist() if n.endswith("SectoralPlans_Catalogues_V1_4.xml"))) as src, open(
            shared_catalogue, "wb"
        ) as dst:
            dst.write(src.read())

    # Source: https://models.geo.admin.ch/SEM/SectoralPlanForAsylum_Catalogues_V1_4.xml
    _merge_ili24_baskets(
        main_xtf, [f"{SOURCE_XTF_DIR}/SectoralPlanForAsylum_Catalogues_V1_4.xml", shared_catalogue], merged_xtf
    )
    tables = _load_sectoral_plan(cur, "spa", model, merged_xtf)

    with open("/loader/post_load_sachplan_asyl.sql") as f:
        cur.execute(f.read().format(**tables))
    cur.execute("SELECT count(*) FROM spa_facility_point")
    print(f"sachplan_asyl: loaded {cur.fetchone()[0]} Facility point rows.", flush=True)


def build_styles() -> None:
    """Write one .sld per DemoSymbology GRAPHIC for pygeoapi's OGC API - Maps providers.

    pycartosym's SLD writer is a hard ili2ogc dependency, so no separate
    install step is needed here beyond the `pip install -e` already run
    for ili2ogc itself.
    """
    os.makedirs("/styles", exist_ok=True)
    for model, sign_xtf, graphic, filename in [
        (SYMBOLOGY_MODEL, SYMBOLOGY_XTF, "Waldabstand_Graphics", "waldabstand.sld"),
        (SYMBOLOGY_MODEL, SYMBOLOGY_XTF, "Roads_Graphics", "roads.sld"),
        (SYMBOLOGY_MODEL, SYMBOLOGY_XTF, "BuildingLines_Graphics", "buildinglines.sld"),
        (SYMBOLOGY_MODEL, SYMBOLOGY_XTF, "Flaeche_Graphics", "flaeche.sld"),
        (SUEL_SYMBOLOGY_MODEL, SUEL_SYMBOLOGY_XTF, "PlanningMeasure_Graphics", "sachplan_uebertragungsleitungen.sld"),
        (SPA_SYMBOLOGY_MODEL, SPA_SYMBOLOGY_XTF, "Facility_Graphics", "sachplan_asyl.sld"),
    ]:
        run(
            [
                "interlis",
                "convert-sld",
                model,
                "--repo",
                REPO,
                "--sign-xtf",
                sign_xtf,
                "--graphic",
                graphic,
                "-o",
                f"/styles/{filename}",
            ]
        )


def main() -> None:
    run(["pip", "install", "--no-cache-dir", "-q", "-e", "/interlis-runtime"])
    import psycopg2  # noqa: PLC0415 (installed above, import after pip install)

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    load_richtplanung(cur)
    load_waldabstandslinien(cur)
    load_mainroads(cur)
    load_buildinglinesformotorways(cur)
    load_sachplan_uebertragungsleitungen(cur)
    load_sachplan_asyl(cur)
    conn.commit()
    cur.close()
    conn.close()
    build_styles()


if __name__ == "__main__":
    main()
