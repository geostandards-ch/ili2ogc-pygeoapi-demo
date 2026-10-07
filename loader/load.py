#!/usr/bin/env python3
"""Loader: one PostGIS schema per collection, created and filled by ili2ogc, then the map styles.

Each `collections/<name>/` holds the collection's VIEWs (`views.ili`), its GRAPHICs (`symbology.ili`) and their
signs (`signs.xtf`); the official models they import are fetched from the INTERLIS model repositories.
"""

import os
import re
import shutil
import subprocess
import zipfile

import psycopg2

COLLECTIONS, MODELS, SOURCES = "/collections", "/tmp/models", "/tmp/sources"

# Each collection's transfers: its data first (validated), then the catalogues its references point into.
TRANSFERS = {
    "richtplanung": ["RichtplanungErneuerbareEnergien_V1_SH.xtf", "RichtplanungErneuerbareEnergien_Katalog.xml"],
    "waldabstandslinien": ["ch_np_wal_v1_2.xtf"],
    "mainroads": ["MainRoads_V1_20210409T091317_LV95.xtf"],
    "buildinglines": ["buildingline_sample_source.xtf"],
    "uebertragungsleitungen": [
        "TransmissionLinesSectoralPlan.xtf",
        "94.1 MeasureTypeCatalogue_V1_4.xml",
        "94.1 FacilityKindCatalogue_V1_4.xml",
        "SectoralPlans_Catalogues_V1_4.xml",
    ],
    "asyl": [
        "sachplan-asyl_kraft_2026-06-19_2056.xtf",
        "SectoralPlanForAsylum_Catalogues_V1_4.xml",
        "SectoralPlans_Catalogues_V1_4.xml",
    ],
    "militaer": [
        "SPM_V1_4_In_Kraft_LV95_mit_Geometrie.xtf",
        "SectoralPlanForMilitaryInfrastructure_Catalogues_V1_4_20250205.xml",
        "SectoralPlans_Catalogues_V1_4.xml",
    ],
}


def interlis(*args: str) -> None:
    """Run an ili2ogc command; exit 2 means completed with notes."""
    print("+ interlis", *args, flush=True)
    if subprocess.run(["interlis", *args]).returncode not in (0, 2):
        raise SystemExit(f"interlis {args[0]} failed")


def unpack_sources() -> None:
    """The source transfers, archives unpacked, side by side."""
    os.makedirs(SOURCES, exist_ok=True)
    for name in os.listdir("/data/source-xtf"):
        path = f"/data/source-xtf/{name}"
        if not name.endswith(".zip"):
            shutil.copy(path, SOURCES)
            continue
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                if member.endswith((".xtf", ".xml")):
                    with open(f"{SOURCES}/{os.path.basename(member)}", "wb") as out:
                        out.write(archive.read(member))


def main() -> None:
    unpack_sources()
    connection = psycopg2.connect(os.environ["DATABASE_URL"])
    connection.autocommit = True  # the data script carries its own transaction
    cursor = connection.cursor()
    for name, transfers in TRANSFERS.items():
        home, files = f"{COLLECTIONS}/{name}", [f"{SOURCES}/{t}" for t in transfers]
        views, symbology, repos = f"{home}/views.ili", f"{home}/symbology.ili", ["--repo", MODELS, "--repo", home]
        interlis("fetch-models", views, symbology, "--repo", home, "-o", MODELS)
        interlis("validate", files[0], "--model", views, *repos)
        interlis("convert-sql", views, *repos, "-o", f"/tmp/{name}_schema.sql")
        interlis("import", *files, "--model", views, *repos, "-o", f"/tmp/{name}_data.sql")
        cursor.execute(f"DROP SCHEMA IF EXISTS {name} CASCADE; CREATE SCHEMA {name}; SET search_path TO {name}, public")
        for part in ("schema", "data"):
            with open(f"/tmp/{name}_{part}.sql") as sql:
                cursor.execute(sql.read())
        cursor.execute("SET search_path TO public")
        with open(symbology) as model:
            graphics = re.findall(r"^\s*GRAPHIC (\w+)", model.read(), re.M)
        for graphic in graphics:
            sld = f"/styles/{name}_{graphic.lower()}.sld"
            interlis("convert-sld", symbology, *repos, "--sign-xtf", f"{home}/signs.xtf", "--graphic", graphic, "-o", sld)
    connection.close()


if __name__ == "__main__":
    main()
