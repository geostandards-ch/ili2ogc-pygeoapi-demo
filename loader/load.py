#!/usr/bin/env python3
"""Loader: build a PostGIS schema from a derived INTERLIS VIEW model via ili2ogc,
load real cantonal geodata into it, and materialize the VIEW itself as a .xtf.

Runs once per `docker-compose up`. ili2ogc's own `convert-jsonfg` does not yet
hoist `GeometryCHLV95_V1.MultiSurface` (a STRUCTURE-wrapped BAG OF SurfaceStructure,
not a native SURFACE/COORD/POLYLINE type) to a JSON-FG top-level "place"/"geometry"
member - the polygon coordinates stay nested under `properties.Geometrie.Surfaces`,
still valid embedded GeoJSON. This loader pulls them out with plain `json` + PostGIS's
own `ST_GeomFromGeoJSON`, independent of that gap.
"""

import json
import os
import subprocess
import urllib.request

MODEL = "/models/RichtplanungErneuerbareEnergien_V1_d_01.ili"
REPO = "/models"
SOURCE_URL = (
    "https://geodienste.ch/downloads/interlis/richtplanung_erneuerbare_energien/SH/"
    "RichtplanungErneuerbareEnergien_V1_SH.xtf"
)
XTF = "/tmp/source.xtf"
SCHEMA_SQL = "/tmp/schema.sql"
DATA_JSONFG = "/tmp/data.jsonfg.json"
VIEW_XTF_OUT = "/data/view_flaeche.materialized.xtf"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def main() -> None:
    run(["pip", "install", "--no-cache-dir", "-q", "-e", "/interlis-runtime"])
    import psycopg2  # noqa: PLC0415 (installed above, import after pip install)

    print(f"Downloading real source .xtf from {SOURCE_URL}", flush=True)
    urllib.request.urlretrieve(SOURCE_URL, XTF)

    run(["interlis", "validate", XTF, "--model", MODEL, "--repo", REPO])
    run(["interlis", "convert-sql", MODEL, "--repo", REPO, "--dialect", "postgresql", "-o", SCHEMA_SQL])
    run(["interlis", "convert-jsonfg", XTF, "--model", MODEL, "--repo", REPO, "-o", DATA_JSONFG])
    run(["interlis", "write-xtf", MODEL, XTF, "--repo", REPO, "-o", VIEW_XTF_OUT])

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    # Idempotent on repeated `docker compose up` against the same postgis volume
    # (dropping/recreating "public" wholesale would also drop the postgis extension).
    cur.execute(
        "DROP VIEW IF EXISTS flaeche_geo CASCADE;"
        "DROP VIEW IF EXISTS view_flaeche CASCADE;"
        "DROP TABLE IF EXISTS flaeche_geometrie_surfaces, flaeche, energieform CASCADE;"
    )

    with open(SCHEMA_SQL) as f:
        cur.execute(f.read())

    # This transfer never carries the external Energieform catalogue basket
    # (see data/NOTICE.md) - the FK/NOT NULL convert-sql derives for it can't
    # be satisfied by this single-file demo.
    cur.execute("ALTER TABLE flaeche DROP CONSTRAINT fk_energieformref_energieform_reference")
    cur.execute("ALTER TABLE flaeche ALTER COLUMN energieform_reference DROP NOT NULL")

    with open(DATA_JSONFG) as f:
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
        for surface in p.get("Geometrie", {}).get("Surfaces", []):
            surface_rows += 1
            cur.execute(
                """INSERT INTO flaeche_geometrie_surfaces (id, flaeche_fk, surface)
                   VALUES (%s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 2056))""",
                (f"surface-{surface_rows}", feat["id"], json.dumps(surface["Surface"])),
            )

    with open("/loader/post_load.sql") as f:
        cur.execute(f.read())

    conn.commit()
    cur.close()
    conn.close()
    print(f"Loaded {flaeche_rows} Flaeche rows, {surface_rows} surfaces.", flush=True)


if __name__ == "__main__":
    main()
