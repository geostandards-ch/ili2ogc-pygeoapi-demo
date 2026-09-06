#!/usr/bin/env python3
"""Compare pygeoapi's own JSON-FG formatter (pygeoapi-plugins) against ili2ogc's
`interlis convert-jsonfg` reference output for the same real objects.

pygeoapi serves the *base* Flaeche class (`flaeche_geo`, with real geometry -
see data/NOTICE.md for why), while data/view_flaeche.jsonfg.json is the
`view_flaeche` VIEW's own attribute-only projection - so this checks the
fields the two share (renamed by the VIEW's own ATTRIBUTE aliases), by
object id, not a full Feature diff.
"""

import json
import sys
import urllib.request

PYGEOAPI_URL = "http://localhost:5000/collections/flaeche_geo/items?f=jsonfg"
REFERENCE_FILE = "data/view_flaeche.jsonfg.json"

# view_flaeche attribute alias -> flaeche_geo (base class) property name
FIELD_MAP = {
    "objektbezeichnung": "objektbezeichnung",
    "objektart": "objektart",
    "genehmigungsdatum": "genehmigungsdatum",
    "beschlussdatum_kanton": "beschlussdatumkanton",
    "weblink": "weblink",
    "kanton": "kanton",
}


def main() -> int:
    with urllib.request.urlopen(PYGEOAPI_URL) as resp:
        pygeoapi_fc = json.load(resp)
    with open(REFERENCE_FILE) as f:
        reference_fc = json.load(f)

    pygeoapi_by_id = {f["id"]: f["properties"] for f in pygeoapi_fc["features"]}
    reference_by_id = {f["id"]: f["properties"] for f in reference_fc["features"]}

    mismatches = 0
    for obj_id, ref_props in reference_by_id.items():
        live_props = pygeoapi_by_id.get(obj_id)
        if live_props is None:
            print(f"MISSING  {obj_id}: not served by pygeoapi's flaeche_geo collection")
            mismatches += 1
            continue
        for view_field, base_field in FIELD_MAP.items():
            ref_value = ref_props.get(view_field)
            live_value = live_props.get(base_field)
            if ref_value != live_value:
                print(f"MISMATCH {obj_id}.{view_field}: reference={ref_value!r} pygeoapi={live_value!r}")
                mismatches += 1

    if mismatches:
        print(f"\n{mismatches} mismatch(es).")
        return 1
    print(f"OK - {len(reference_by_id)} object(s), all shared fields match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
