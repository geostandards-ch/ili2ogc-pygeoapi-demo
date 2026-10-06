#!/usr/bin/env python3
"""Loader: build one PostGIS schema per collection via ili2ogc, load real geodata into it, write the styles.

Runs once per `docker-compose up`. Each `collections/<name>/` directory holds
a collection's `views.ili` (its map VIEWs over the official data model),
`symbology.ili` (GRAPHICs based on those VIEWs) and `signs.xtf`. Each
collection gets its own PostgreSQL schema holding exactly what
`interlis convert-sql` generates from `views.ili` - ili2db's layout (`t_id`,
`t_basket`, `t_ili_tid`, the `T_ILI2DB_*` tables), one SQL view per VIEW
that the matching SLD's filters are evaluated on, and one readable
`<table>_features` view per table, with catalogue keys and German names in
place of raw references (`--feature-views de`). No hand-written SQL:
pygeoapi serves the generated views as they are.
"""

import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

REPO = "/models"
COLLECTIONS = "/collections"
SOURCE_XTF_DIR = "/data/source-xtf"
_ILI23_NS = "http://www.interlis.ch/INTERLIS2.3"


def run(cmd: list[str], accept_degraded: bool = False) -> None:
    """Run an ili2ogc command; exit 2 (completed, notes/warnings only) passes only if `accept_degraded`."""
    print("+", " ".join(cmd), flush=True)
    returncode = subprocess.run(cmd).returncode
    if returncode not in ((0, 2) if accept_degraded else (0,)):
        raise subprocess.CalledProcessError(returncode, cmd)


def _repos(name: str) -> list[str]:
    """The official models plus the collection's own directory (its views.ili, imported by symbology.ili)."""
    return ["--repo", REPO, "--repo", f"{COLLECTIONS}/{name}"]


def prepare(name: str, xtf: str) -> tuple[str, dict]:
    """Validate the transfer, generate the collection's schema (with its map views) and its JSON-FG.

    `views.ili` EXTENDS the data topic, so every class of the data model gets its table, not only the
    projected ones. `convert-sql` exits 2 (completed, notes only) on these models: e.g. CHBase lines admit
    arcs the linear columns can't hold, which `Dataset.geometry` strokes on load as the note asks.
    """
    model = f"{COLLECTIONS}/{name}/views.ili"
    schema_sql, data_jsonfg = f"/tmp/{name}_schema.sql", f"/tmp/{name}_data.jsonfg.json"
    run(["interlis", "validate", xtf, "--model", model, *_repos(name)])
    run(
        ["interlis", "convert-sql", model, *_repos(name), "--feature-views", "de", "-o", schema_sql],
        accept_degraded=True,
    )
    run(["interlis", "convert-jsonfg", xtf, "--model", model, *_repos(name), "-o", data_jsonfg])
    with open(data_jsonfg) as f:
        features = json.load(f)["features"]
    by_type: dict[str, list[dict]] = {}
    for feat in features:
        by_type.setdefault(feat["featureType"], []).append(feat)
    return schema_sql, by_type


def _wkt(geometry: dict, tagged: bool = True) -> str:
    """A JSON-FG geometry, curves included, as WKT (PostGIS's untagged form for parts of a curved geometry)."""
    kind = geometry["type"]

    def points(coordinates: list) -> str:
        return "(" + ", ".join(" ".join(str(v) for v in xy) for xy in coordinates) + ")"

    def rings(polygon: list) -> str:
        return "(" + ", ".join(points(ring) for ring in polygon) + ")"

    coordinates = geometry.get("coordinates")
    if kind == "Point":
        return f"POINT {points([coordinates])}"
    if kind == "LineString":
        return f"LINESTRING {points(coordinates)}" if tagged else points(coordinates)
    if kind == "CircularString":
        return f"CIRCULARSTRING {points(coordinates)}"
    if kind == "Polygon":
        return f"POLYGON {rings(coordinates)}" if tagged else rings(coordinates)
    if kind == "MultiPoint":
        return "MULTIPOINT (" + ", ".join(points([xy]) for xy in coordinates) + ")"
    if kind == "MultiLineString":
        return "MULTILINESTRING (" + ", ".join(points(line) for line in coordinates) + ")"
    if kind == "MultiPolygon":
        return "MULTIPOLYGON (" + ", ".join(rings(polygon) for polygon in coordinates) + ")"
    nested = kind != "GeometryCollection"  # CompoundCurve, CurvePolygon, MultiCurve, MultiSurface
    return f"{kind.upper()} (" + ", ".join(_wkt(g, tagged=not nested) for g in geometry["geometries"]) + ")"


def _parts(structure: dict | None, list_key: str, item_key: str) -> dict | None:
    """A CHBase multi-geometry STRUCTURE value (`{"Points": [{"Point": {...}}]}`) as one GeometryCollection."""
    parts = [item[item_key] for item in (structure or {}).get(list_key) or [] if item.get(item_key)]
    return {"type": "GeometryCollection", "geometries": parts} if parts else None


def _xtf_baskets(path: str) -> list[tuple[str, str, list[str]]]:
    """(BID, topic, object TIDs) of every basket of an INTERLIS 2.3 transfer."""
    data = ET.parse(path).getroot().find(f"{{{_ILI23_NS}}}DATASECTION")
    return [
        (basket.get("BID"), basket.tag.removeprefix(f"{{{_ILI23_NS}}}"), [o.get("TID") for o in basket if o.get("TID")])
        for basket in data
    ]


class Dataset:
    """One transfer in its own PostgreSQL schema: a T_ILI2DB_DATASET row, one T_ILI2DB_BASKET row per basket.

    Objects are inserted with their basket and TID; `ref` turns a transferred TID into the referenced row's
    `t_id`, so rows go in reference order (catalogues first).
    """

    def __init__(self, cur, schema: str, schema_sql: str, xtf: str):
        self.cur = cur
        cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE; CREATE SCHEMA {schema}; SET search_path TO {schema}, public;")
        with open(schema_sql) as f:
            cur.execute(f.read())
        cur.execute(
            "INSERT INTO T_ILI2DB_DATASET (T_Id, datasetName) VALUES (nextval('t_ili2db_seq'), %s) RETURNING T_Id",
            (schema,),
        )
        dataset = cur.fetchone()[0]
        self.basket_of: dict[str, int] = {}
        for bid, topic, tids in _xtf_baskets(xtf):
            cur.execute(
                """INSERT INTO T_ILI2DB_BASKET (T_Id, dataset, topic, T_Ili_Tid, attachmentKey)
                   VALUES (nextval('t_ili2db_seq'), %s, %s, %s, %s) RETURNING T_Id""",
                (dataset, topic, bid, os.path.basename(xtf)),
            )
            basket = cur.fetchone()[0]
            self.basket_of.update(dict.fromkeys(tids, basket))
        self.t_id: dict[str, int] = {}
        self.table_of: dict[str, str] = {}
        self.counts: dict[str, int] = {}

    def ref(self, tid: str | None) -> int | None:
        return None if tid is None else self.t_id[tid]

    def link(self, column: str, tid: str | None, base_table: str) -> dict:
        """A reference whose target may be a subclass: convert-sql gives each other target table its own
        `<column>_<table>` column."""
        if tid is None:
            return {}
        table = self.table_of[tid]
        return {column if table == base_table else f"{column}_{table}": self.t_id[tid]}

    @staticmethod
    def geometry(value: dict | None, srid: int = 2056, multi: int | None = None) -> tuple[str, str | None]:
        """A geometry parameter, arcs stroked (the linear columns' SQL-GEOM-ARCS-STROKED note).

        `multi` is the ST_CollectionExtract type (1 point, 2 line, 3 polygon) of a Multi* column.
        """
        sql = f"ST_GeomFromText(%s, {srid})"
        if multi != 1:
            sql = f"ST_CurveToLine({sql})"
        if multi:
            sql = f"ST_Multi(ST_CollectionExtract({sql}, {multi}))"
        return sql, None if value is None else _wkt(value)

    def insert(self, table: str, feat: dict, **columns) -> int:
        """INSERT one object; a `(sql, param)` value is a SQL expression (see `geometry`)."""
        names = ["t_basket", "t_ili_tid", *columns]
        sql_values = ["%s", "%s"]
        params = [self.basket_of[feat["id"]], feat["id"]]
        for value in columns.values():
            sql, param = value if isinstance(value, tuple) else ("%s", value)
            sql_values.append(sql)
            params.append(param)
        self.cur.execute(
            f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join(sql_values)}) RETURNING t_id", params
        )
        self.t_id[feat["id"]] = t_id = self.cur.fetchone()[0]
        self.table_of[feat["id"]] = table
        self.counts[table] = self.counts.get(table, 0) + 1
        return t_id

    def localised(self, table: str, attribute: str, owner: int, feat: dict, value: dict | None) -> None:
        """A LocalisationCH MultilingualText value: one row per language in its child table."""
        for text in (value or {}).get("LocalisedText") or []:
            self.cur.execute(
                f"""INSERT INTO {table}_{attribute}_localisedtext (t_basket, {table}_fk, language, text)
                    VALUES (%s, %s, %s, %s)""",
                (self.basket_of[feat["id"]], owner, text.get("Language"), text["Text"]),
            )

    def done(self, name: str) -> None:
        self.cur.execute("SET search_path TO public;")
        print(f"{name}: " + ", ".join(f"{n} {t}" for t, n in self.counts.items()), flush=True)


def _merge_ili23_baskets(main_path: str, extra_paths: list[str], out_path: str) -> None:
    """Merge extra `.xtf`/catalogue `.xml` transfers into `main_path`'s own `DATASECTION`.

    `REFERENCE TO (EXTERNAL)` only resolves within objects present in the
    SAME parsed transfer, so the main dataset and its separate catalogue
    files need combining first.
    """
    ET.register_namespace("", _ILI23_NS)
    main_tree = ET.parse(main_path)
    main_data = main_tree.getroot().find(f"{{{_ILI23_NS}}}DATASECTION")
    main_basket = next(iter(main_data))

    for extra_path in extra_paths:
        extra_data = ET.parse(extra_path).getroot().find(f"{{{_ILI23_NS}}}DATASECTION")
        for extra_basket in list(extra_data):
            if extra_basket.tag == main_basket.tag and extra_basket.get("BID") == main_basket.get("BID"):
                for child in list(extra_basket):
                    main_basket.append(child)
            else:
                main_data.append(extra_basket)

    main_tree.write(out_path, encoding="UTF-8", xml_declaration=True)


def load_richtplanung(cur) -> None:
    """`RichtplanungErneuerbareEnergien_V1` (real SH data: Flaeche and Punkt) with the BFE Energieform catalogue."""
    xtf = "/tmp/richtplanung_source.xtf"
    # Sources: https://geodienste.ch/downloads/interlis/richtplanung_erneuerbare_energien/SH/RichtplanungErneuerbareEnergien_V1_SH.xtf
    # and https://models.geo.admin.ch/BFE/RichtplanungErneuerbareEnergien_Katalog.xml
    _merge_ili23_baskets(
        f"{SOURCE_XTF_DIR}/RichtplanungErneuerbareEnergien_V1_SH.xtf",
        [f"{SOURCE_XTF_DIR}/RichtplanungErneuerbareEnergien_Katalog.xml"],
        xtf,
    )
    schema_sql, by_type = prepare("richtplanung", xtf)
    ds = Dataset(cur, "richtplanung", schema_sql, xtf)
    for feat in by_type.get("Energieform", []):
        ds.insert("energieform", feat, energieform=feat["properties"]["Energieform"])
    for feat in by_type.get("Flaeche", []):
        p = feat["properties"]
        ds.insert(
            "flaeche",
            feat,
            energieform_reference=ds.ref(p["Energieform"]),
            objektbezeichnung=p.get("Objektbezeichnung"),
            beschrieb=p.get("Beschrieb"),
            objektart=p.get("Objektart"),
            genehmigungsdatum=p.get("Genehmigungsdatum"),
            beschlussdatumkanton=p.get("BeschlussdatumKanton"),
            kanton=p.get("Kanton"),
            weblink=p.get("Weblink"),
            bemerkungen=p.get("Bemerkungen"),
            geometrie=ds.geometry(feat.get("place"), multi=3),
        )
    for feat in by_type.get("Punkt", []):
        p = feat["properties"]
        ds.insert(
            "punkt",
            feat,
            energieform_reference=ds.ref(p["Energieform"]),
            objektbezeichnung=p.get("Objektbezeichnung"),
            beschrieb=p.get("Beschrieb"),
            objektart=p.get("Objektart"),
            genehmigungsdatum=p.get("Genehmigungsdatum"),
            beschlussdatumkanton=p.get("BeschlussdatumKanton"),
            kanton=p.get("Kanton"),
            weblink=p.get("Weblink"),
            bemerkungen=p.get("Bemerkungen"),
            # Punkt.Geometrie is the CHBase MultiPoint STRUCTURE, left in properties.
            geometrie=ds.geometry(_parts(p.get("Geometrie"), "Points", "Point"), multi=1),
        )
    ds.done("richtplanung")


def load_waldabstandslinien(cur) -> None:
    """`Waldabstandslinien_V1_2` (real GL data)."""
    # Source: https://www.geodienste.ch/downloads/interlis/npl_waldabstandslinien/GL/ch_np_wal_v1_2.xtf
    xtf = "/tmp/waldabstandslinien_source.xtf"
    shutil.copy(f"{SOURCE_XTF_DIR}/ch_np_wal_v1_2.xtf", xtf)
    schema_sql, by_type = prepare("waldabstandslinien", xtf)
    ds = Dataset(cur, "waldabstandslinien", schema_sql, xtf)
    for feat in by_type.get("Typ", []):
        p = feat["properties"]
        ds.insert(
            "typ",
            feat,
            code=p.get("Code"),
            bezeichnung=p.get("Bezeichnung"),
            abkuerzung=p.get("Abkuerzung"),
            verbindlichkeit=p.get("Verbindlichkeit"),
            bemerkungen=p.get("Bemerkungen"),
        )
    for feat in by_type.get("Waldabstand_Linie", []):
        p = feat["properties"]
        ds.insert(
            "waldabstand_linie",
            feat,
            geometrie=ds.geometry(feat.get("place")),
            publiziertab=p.get("publiziertAb"),
            publiziertbis=p.get("publiziertBis"),
            rechtsstatus=p.get("Rechtsstatus"),
            bemerkungen=p.get("Bemerkungen"),
            wal=ds.ref(p.get("WAL")),
        )
    ds.done("waldabstandslinien")


def load_mainroads(cur) -> None:
    """`MainRoads_LV95_V1_1` (real Swiss-wide data); the source is a ZIP."""
    # Source: https://data.geo.admin.ch/ch.astra.hauptstrassennetz/hauptstrassennetz/hauptstrassennetz_2056.xtf.zip
    xtf = "/tmp/mainroads_source.xtf"
    with zipfile.ZipFile(f"{SOURCE_XTF_DIR}/hauptstrassennetz_2056.xtf.zip") as zf:
        (xtf_member,) = [n for n in zf.namelist() if n.endswith(".xtf")]
        with zf.open(xtf_member) as src, open(xtf, "wb") as dst:
            dst.write(src.read())
    schema_sql, by_type = prepare("mainroads", xtf)
    ds = Dataset(cur, "mainroads", schema_sql, xtf)
    for feat in by_type.get("RoadSegment", []):
        p = feat["properties"]
        ds.insert(
            "roadsegment",
            feat,
            geometry=ds.geometry(feat.get("place")),
            canton=p.get("Canton"),
            roadnumber=p.get("RoadNumber"),
            segmentdescription=p.get("SegmentDescription"),
        )
    ds.done("mainroads")


def load_buildinglinesformotorways(cur) -> None:
    """`BuildingLinesForMotorways_V2_2` (real ASTRA data, lines with ARC segments).

    The real source (3686 objects, 9.5 MB) is too large for this repository:
    `data/buildingline_sample_source.xtf` is a 30-object sample, 15 straight
    and 15 with arcs (full source: https://data.geo.admin.ch/ch.astra.baulinien-nationalstrassen).
    The arcs are stroked into the linear column; GeoJSON has no curves anyway.
    """
    xtf = "/data/buildingline_sample_source.xtf"
    schema_sql, by_type = prepare("buildinglines", xtf)
    ds = Dataset(cur, "buildinglines", schema_sql, xtf)
    for feat in by_type.get("BuildingLine", []):
        p = feat["properties"]
        ds.insert(
            "buildingline",
            feat,
            geometry=ds.geometry(feat.get("place")),
            status=p.get("Status"),
            approvaldate=p.get("ApprovalDate"),
            approvingauthority=p.get("ApprovingAuthority"),
            planningapprovalname=p.get("PlanningApprovalName"),
            publicationdatefrom=p.get("PublicationDateFrom"),
            publicationdateto=p.get("PublicationDateTo"),
            weblink=p.get("WebLink"),
        )
    ds.done("buildinglines")


# (feature type, table, catalogue id column, JSON-FG property) - the base model's catalogues.
_SECTORAL_PLAN_CATALOGUES = [
    ("FacilityKind", "facilitykind", "kindid", "KindID"),
    ("FacilityStatus", "facilitystatus", "statusid", "StatusID"),
    ("MeasureType", "measuretype", "typeid", "TypeID"),
    ("CoordinationLevel", "coordinationlevel", "coordid", "CoordID"),
    ("PlanningStatus", "planningstatus", "statusid", "StatusID"),
]


def _mod_info(p: dict) -> dict:
    mod_info = p.get("ModInfo") or {}
    return {
        "modinfo_validfrom": mod_info.get("ValidFrom"),
        "modinfo_validuntil": mod_info.get("ValidUntil"),
        "modinfo_latestmodification": mod_info.get("LatestModification"),
    }


def _load_sectoral_plan(cur, schema: str, xtf: str, subclasses: dict | None = None) -> None:
    """A `BaseModel_SectoralPlans_V1_4` transfer: catalogues, SectoralPlan, Object, Facility, PlanningMeasure.

    `subclasses` maps a theme's own Object/Facility subclass (feature type) to its table
    stem and own columns, e.g. Sachplan Militaer's `Facility_SPM`.
    """
    schema_sql, by_type = prepare(schema, xtf)
    ds = Dataset(cur, schema, schema_sql, xtf)
    plan, obj, facility, measure = "sectoralplan", "object", "facility", "planningmeasure"
    point, line = (lambda p: _parts(p.get("Point"), "Points", "Point")), (lambda p: _parts(p.get("Line"), "Lines", "Line"))

    def features_of(base_type: str, base_table: str):
        """The base class's objects, then each subclass's, with their table and own columns."""
        yield from ((f, base_table, {}) for f in by_type.get(base_type, []))
        for feature_type, (base, stem, own) in (subclasses or {}).items():
            if base == base_type:
                for f in by_type.get(feature_type, []):
                    yield f, stem, {c: f["properties"].get(prop) for c, prop in own.items()}

    for feature_type, table, id_column, prop in _SECTORAL_PLAN_CATALOGUES:
        for feat in by_type.get(feature_type, []):
            t_id = ds.insert(table, feat, **{id_column: feat["properties"][prop]})
            ds.localised(table, "name", t_id, feat, feat["properties"].get("Name"))
    for feat in by_type.get("SectoralPlan", []):
        p = feat["properties"]
        t_id = ds.insert(plan, feat, geoiv_id=p["GeoIV_ID"], **_mod_info(p))
        ds.localised(plan, "name", t_id, feat, p.get("Name"))
    for feat, table, own in features_of("Object", obj):
        p = feat["properties"]
        t_id = ds.insert(table, feat, sectoralplan=ds.ref(p["SectoralPlan"]), **own, **_mod_info(p))
        ds.localised(table, "name", t_id, feat, p.get("Name"))
    for feat, table, own in features_of("Facility", facility):
        p = feat["properties"]
        t_id = ds.insert(
            table,
            feat,
            facilitykind_reference=ds.ref(p["FacilityKind"]),
            facilitystatus_reference=ds.ref(p["FacilityStatus"]),
            symbolori=p.get("SymbolOri"),
            **ds.link("object", p.get("Object"), obj),
            point=ds.geometry(point(p), multi=1),
            line=ds.geometry(line(p), multi=2),
            **own,
            **_mod_info(p),
        )
        ds.localised(table, "name", t_id, feat, p.get("Name"))
    for feat in by_type.get("PlanningMeasure", []):
        p = feat["properties"]
        t_id = ds.insert(
            measure,
            feat,
            measuretype_reference=ds.ref(p["MeasureType"]),
            coordinationlevel_reference=ds.ref(p["CoordinationLevel"]),
            planningstatus_reference=ds.ref(p["PlanningStatus"]),
            symbolori=p.get("SymbolOri"),
            **ds.link("facility", p.get("Facility"), facility),
            point=ds.geometry(point(p), multi=1),
            line=ds.geometry(line(p), multi=2),
            # PlanningMeasure.Surface is hoisted to "place".
            surface=ds.geometry(feat.get("place"), multi=3),
            **_mod_info(p),
        )
        ds.localised(measure, "name", t_id, feat, p.get("Name"))
    ds.done(schema)


def load_sachplan_uebertragungsleitungen(cur) -> None:
    """`TransmissionLinesSectoralPlan_V1_4` (Sachplan Übertragungsleitungen, real BFE data) and its 3 catalogues."""
    main_xtf = "/tmp/suel_main.xtf"
    catalogues = ["/tmp/suel_measuretype.xml", "/tmp/suel_facilitykind.xml", "/tmp/suel_shared.xml"]
    merged_xtf = "/tmp/sachplan_uebertragungsleitungen.merged.xtf"

    # Source: https://data.geo.admin.ch/ch.bfe.sachplan-uebertragungsleitungen_kraft/
    # sachplan-uebertragungsleitungen_kraft/sachplan-uebertragungsleitungen_kraft_2056.xtf.zip
    with zipfile.ZipFile(f"{SOURCE_XTF_DIR}/sachplan-uebertragungsleitungen_kraft_2056.xtf.zip") as zf:
        members = [
            next(n for n in zf.namelist() if n.endswith("TransmissionLinesSectoralPlan.xtf")),
            next(n for n in zf.namelist() if "MeasureTypeCatalogue" in n),
            next(n for n in zf.namelist() if "FacilityKindCatalogue" in n),
            next(n for n in zf.namelist() if n.endswith("SectoralPlans_Catalogues_V1_4.xml")),
        ]
        for member, path in zip(members, [main_xtf, *catalogues]):
            with zf.open(member) as src, open(path, "wb") as dst:
                dst.write(src.read())

    _merge_ili23_baskets(main_xtf, catalogues, merged_xtf)
    _load_sectoral_plan(cur, "uebertragungsleitungen", merged_xtf)


def load_sachplan_asyl(cur) -> None:
    """`SectoralPlanForAsylum_LV95_V1_4` (Sachplan Asyl, real SEM data).

    The SEM catalogue (FacilityKind) is vendored next to the data; the
    cross-Sachplan catalogue (FacilityStatus) is the same file
    Übertragungsleitungen ships, read from its archive.
    """
    main_xtf = "/tmp/spa_main.xtf"
    shared_catalogue = "/tmp/spa_shared_catalogue.xml"
    merged_xtf = "/tmp/sachplan_asyl.merged.xtf"

    # Source: https://data.geo.admin.ch/ch.sem.sachplan-asyl_kraft/sachplan-asyl_kraft/sachplan-asyl_kraft_2056.zip
    with zipfile.ZipFile(f"{SOURCE_XTF_DIR}/sachplan-asyl_kraft_2056.zip") as zf:
        with zf.open(next(n for n in zf.namelist() if n.endswith(".xtf"))) as src, open(main_xtf, "wb") as dst:
            dst.write(src.read())
    with zipfile.ZipFile(f"{SOURCE_XTF_DIR}/sachplan-uebertragungsleitungen_kraft_2056.xtf.zip") as zf:
        member = next(n for n in zf.namelist() if n.endswith("SectoralPlans_Catalogues_V1_4.xml"))
        with zf.open(member) as src, open(shared_catalogue, "wb") as dst:
            dst.write(src.read())

    # Source: https://models.geo.admin.ch/SEM/SectoralPlanForAsylum_Catalogues_V1_4.xml
    _merge_ili23_baskets(
        main_xtf, [f"{SOURCE_XTF_DIR}/SectoralPlanForAsylum_Catalogues_V1_4.xml", shared_catalogue], merged_xtf
    )
    _load_sectoral_plan(cur, "asyl", merged_xtf)


def load_sachplan_militaer(cur) -> None:
    """`SectoralPlanForMilitaryInfrastructure_LV95_V1_4` (Sachplan Militär, real armasuisse/VBS data).

    The published XTF carries every object but no coordinates (empty Point/
    Surface structures); `data/source-xtf/SPM_V1_4_In_Kraft_LV95_mit_Geometrie.xtf.zip`
    is that XTF completed with the geometries of the same dataset's GDB
    export, matched by TID (`tools/complete_militaer_xtf.py`; ilivalidator:
    0 errors). Its own `Object_SPM`/`Facility_SPM` subclasses carry an
    object/facility number.
    """
    main_xtf = "/tmp/spm_main.xtf"
    shared_catalogue = "/tmp/spm_shared_catalogue.xml"
    merged_xtf = "/tmp/sachplan_militaer.merged.xtf"

    # Sources: https://data.geo.admin.ch/ch.vbs.sachplan-infrastruktur-militaer_kraft/
    # sachplan-infrastruktur-militaer_kraft/sachplan-infrastruktur-militaer_kraft_2056.{xtf,gdb}.zip
    with zipfile.ZipFile(f"{SOURCE_XTF_DIR}/SPM_V1_4_In_Kraft_LV95_mit_Geometrie.xtf.zip") as zf:
        with zf.open(next(n for n in zf.namelist() if n.endswith(".xtf"))) as src, open(main_xtf, "wb") as dst:
            dst.write(src.read())
    with zipfile.ZipFile(f"{SOURCE_XTF_DIR}/sachplan-uebertragungsleitungen_kraft_2056.xtf.zip") as zf:
        member = next(n for n in zf.namelist() if n.endswith("SectoralPlans_Catalogues_V1_4.xml"))
        with zf.open(member) as src, open(shared_catalogue, "wb") as dst:
            dst.write(src.read())

    # Source: https://models.geo.admin.ch/VBS/SectoralPlanForMilitaryInfrastructure_Catalogues_V1_4_20250205.xml
    _merge_ili23_baskets(
        main_xtf,
        [f"{SOURCE_XTF_DIR}/SectoralPlanForMilitaryInfrastructure_Catalogues_V1_4_20250205.xml", shared_catalogue],
        merged_xtf,
    )
    _load_sectoral_plan(
        cur,
        "militaer",
        merged_xtf,
        subclasses={
            "Object_SPM": ("Object", "object_spm", {"objectnumber_spm": "ObjectNumber_SPM"}),
            "Facility_SPM": ("Facility", "facility_spm", {"facilitynumber_spm": "FacilityNumber_SPM"}),
        },
    )


def build_styles() -> None:
    """Write one .sld per GRAPHIC of each collection's symbology, for pygeoapi's OGC API - Maps providers."""
    os.makedirs("/styles", exist_ok=True)
    for name in sorted(os.listdir(COLLECTIONS)):
        symbology = f"{COLLECTIONS}/{name}/symbology.ili"
        with open(symbology) as f:
            graphics = re.findall(r"^\s*GRAPHIC (\w+)", f.read(), re.M)
        for graphic in graphics:
            run(
                [
                    "interlis", "convert-sld", symbology, *_repos(name),
                    "--sign-xtf", f"{COLLECTIONS}/{name}/signs.xtf", "--graphic", graphic,
                    "-o", f"/styles/{name}_{graphic.lower()}.sld",
                ]
            )


def main() -> None:
    import psycopg2  # noqa: PLC0415 (only in the loader image, keeps this module importable without it)

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    load_richtplanung(cur)
    load_waldabstandslinien(cur)
    load_mainroads(cur)
    load_buildinglinesformotorways(cur)
    load_sachplan_uebertragungsleitungen(cur)
    load_sachplan_asyl(cur)
    load_sachplan_militaer(cur)
    conn.commit()
    cur.close()
    conn.close()
    build_styles()


if __name__ == "__main__":
    main()
