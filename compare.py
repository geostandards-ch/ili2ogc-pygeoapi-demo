#!/usr/bin/env python3
"""Compare pygeoapi's own JSON-FG formatter (pygeoapi-plugins) against ili2ogc's
`interlis convert-jsonfg` reference output for the same real objects, for each
collection this demo serves.

Each pygeoapi collection is a hand-written convenience view (a base class, or
a base class + id joined back onto the auto-generated VIEW) rather than the
VIEW verbatim - see data/NOTICE.md for why - so this checks the fields the
two share (renamed by the VIEW's own ATTRIBUTE aliases where they differ), by
object id, not a full Feature diff.
"""

import json
import sys
import urllib.request

COMPARISONS = [
    {
        "name": "flaeche_geo / view_flaeche",
        "pygeoapi_url": "http://localhost:5000/collections/flaeche_geo/items?f=jsonfg",
        "reference_file": "data/view_flaeche.jsonfg.json",
        # view_flaeche attribute alias -> flaeche_geo (base class) property name
        "field_map": {
            "objektbezeichnung": "objektbezeichnung",
            "objektart": "objektart",
            "genehmigungsdatum": "genehmigungsdatum",
            "beschlussdatum_kanton": "beschlussdatumkanton",
            "weblink": "weblink",
            "kanton": "kanton",
        },
    },
    {
        "name": "waldabstand_geo / view_waldabstand_linie",
        "pygeoapi_url": (
            "http://localhost:5000/collections/waldabstand_geo/items?f=jsonfg"
            "&crs=http://www.opengis.net/def/crs/EPSG/0/2056"
        ),
        "reference_file": "data/view_waldabstand_linie.jsonfg.json",
        # waldabstand_geo reuses the VIEW's own attribute names verbatim (no renaming needed).
        "field_map": {
            "publiziertab": "publiziertab",
            "rechtsstatus": "rechtsstatus",
            "code": "code",
            "bezeichnung": "bezeichnung",
            "verbindlichkeit": "verbindlichkeit",
        },
        # view_waldabstand_linie carries no "id" (see data/NOTICE.md) - match by geometry instead.
        "match_by": "geometry",
    },
    {
        "name": "mainroads / view_roadsegment",
        "pygeoapi_url": "http://localhost:5000/collections/mainroads/items?f=jsonfg&limit=200",
        "reference_file": "data/view_roadsegment.jsonfg.json",
        # view_roadsegment reuses the VIEW's own attribute names verbatim (no renaming needed).
        "field_map": {
            "roadnumber": "roadnumber",
            "segmentdescription": "segmentdescription",
            "canton": "canton",
        },
    },
    {
        "name": "buildinglines / view_buildingline",
        "pygeoapi_url": "http://localhost:5000/collections/buildinglines/items?f=jsonfg&limit=100",
        "reference_file": "data/view_buildingline.jsonfg.json",
        # view_buildingline attribute alias -> buildingline_geo (base class) column name
        "field_map": {
            "approving_authority": "approvingauthority",
            "status": "status",
            "approval_date": "approvaldate",
            "planning_approval_name": "planningapprovalname",
            "publication_date_from": "publicationdatefrom",
        },
    },
]


def _by_id(features: list[dict]) -> dict:
    return {f["id"]: f["properties"] for f in features}


def _by_geometry(features: list[dict]) -> dict:
    return {json.dumps(f.get("place") or f.get("geometry")): f["properties"] for f in features}


def run_comparison(spec: dict) -> int:
    with urllib.request.urlopen(spec["pygeoapi_url"]) as resp:
        pygeoapi_fc = json.load(resp)
    with open(spec["reference_file"]) as f:
        reference_fc = json.load(f)

    key_fn = _by_geometry if spec.get("match_by") == "geometry" else _by_id
    pygeoapi_by_key = key_fn(pygeoapi_fc["features"])
    reference_by_key = key_fn(reference_fc["features"])

    mismatches = 0
    for key, ref_props in reference_by_key.items():
        live_props = pygeoapi_by_key.get(key)
        if live_props is None:
            print(f"[{spec['name']}] MISSING {key}: not served by pygeoapi")
            mismatches += 1
            continue
        for view_field, base_field in spec["field_map"].items():
            ref_value = ref_props.get(view_field)
            live_value = live_props.get(base_field)
            if ref_value != live_value:
                print(f"[{spec['name']}] MISMATCH {key}.{view_field}: reference={ref_value!r} pygeoapi={live_value!r}")
                mismatches += 1

    if mismatches:
        print(f"[{spec['name']}] {mismatches} mismatch(es).")
    else:
        print(f"[{spec['name']}] OK - {len(reference_by_key)} object(s), all shared fields match.")
    return mismatches


def main() -> int:
    total_mismatches = sum(run_comparison(spec) for spec in COMPARISONS)
    return 1 if total_mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
