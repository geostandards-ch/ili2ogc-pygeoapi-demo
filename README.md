# ili2ogc pygeoapi demo

A live [pygeoapi](https://pygeoapi.io) OGC API Features service backed by a
PostGIS schema generated from a real INTERLIS model with
[ili2ogc](https://github.com/maxcollombin/ili2ogc), a pure-Python INTERLIS 2
toolkit. Real cantonal geodata, not synthetic fixtures.

## Why

ili2ogc already cross-checks its own two conversion paths against each other
for derived VIEW models: `convert-sql` (a real PostGIS `CREATE VIEW`) against
`convert-jsonfg` (in-memory VIEW evaluation) - see
[`docs/verified-view-corpus.md`](https://github.com/maxcollombin/ili2ogc/blob/main/docs/verified-view-corpus.md)
in the main repo. This demo adds `pygeoapi`'s own independent JSON-FG
formatter ([`pygeoapi-plugins`](https://github.com/cgs-earth/pygeoapi-plugins))
as a 3rd, unrelated implementation reading the SAME PostGIS data - a
disagreement between the three would point to a real bug or a genuine
standard-interpretation gap, in either tool.

It also shows `interlis write-xtf --merge-with-source`: since XTF is XML,
a derived model's materialized `.xtf` can extend the base transfer rather
than replace it - each `data/*.xtf` here is the real source data's own
baskets with the computed VIEW basket appended, one self-describing file
(refman eCH-0031 V2.1.0 §4.3.5 explicitly allows a transfer to hold
baskets from several models).

## Models

- [`RichtplanungErneuerbareEnergien_V1`](https://models.geo.admin.ch/BFE/)
  (BFE) - renewable-energy spatial planning, real data for canton
  Schaffhausen (3 objects). `view_flaeche`
  (`RichtplanungErneuerbareEnergien_V1_d_01.ili`) is a plain `PROJECTION OF`
  a single class.
- [`Waldabstandslinien_V1_2`](https://models.geo.admin.ch/BAFU/) (BAFU) -
  forest-distance lines, real data for canton Glarus (5 objects).
  `view_waldabstand_linie` (`Waldabstandslinien_V1_2_d.ili`) is a `JOIN OF
  Waldabstand_Linie, Typ` - unlike the Richtplanung Projection, its own
  `ATTRIBUTE` block maps the geometry through directly, so `convert-sql`'s
  `CREATE VIEW` already carries a real geometry column (no base-table
  workaround needed for this one).
- [`MainRoads_LV95_V1_1`](https://models.geo.admin.ch/ASTRA/) (ASTRA) -
  Swiss-wide main road segments, real data (135 objects). `view_roadsegment`
  (`MainRoads_LV95_V1_1_d.ili`) is another plain Projection, but its
  geometry is a native 3D `LineType` (not a `MultiSurface`), so
  `convert-sql` puts a real `geometry(LineStringZ, 2056)` column directly
  on the base table - pygeoapi is pointed at that table with no convenience
  view needed at all.
- [`BuildingLinesForMotorways_V2_2`](https://models.geo.admin.ch/ASTRA/)
  (ASTRA) - building-restriction lines along motorways, a curated
  30-object sample of the real Swiss-wide data (3686 objects - too large
  to commit whole, see [`data/NOTICE.md`](data/NOTICE.md)). The first
  model here whose geometry has real `ARC` segments -
  `view_buildingline`'s `"place"` is `CircularString`/`CompoundCurve`,
  not just `LineString`. Surfaced 3 real, documented findings around
  curved geometry (`convert-sql`'s column typing, `ST_GeomFromGeoJSON`
  vs. WKT, GeoJSON having no curve types at all) - see
  [`data/NOTICE.md`](data/NOTICE.md).

All 4 already verified end-to-end (SQL and JSON-FG identical) in the main
`ili2ogc` repo. See [`data/NOTICE.md`](data/NOTICE.md) for full provenance
and the documented gaps/findings this demo worked around.

## Running it

Requires a local checkout of
[`ili2ogc`](https://github.com/maxcollombin/ili2ogc) as a sibling directory
(`../interlis-runtime`) - the package isn't published to PyPI yet, so
`docker-compose.yml` mounts it and installs it editable inside the `loader`
container. Once published, swap that volume mount for a plain
`pip install ili2ogc` in `loader/Dockerfile`.

```bash
docker compose up --build
```

- `loader` downloads 3 real source files (2 `.xtf`, 1 `.xtf.zip`) and
  reads the 4th's committed sample directly (`buildingline_sample_source.
  xtf` - see [`data/NOTICE.md`](data/NOTICE.md) for why), builds the
  PostGIS schema for each model (`interlis convert-sql`), loads them, and
  materializes each VIEW as a `.xtf` (`interlis write-xtf
  --merge-with-source`), then exits.
- `pygeoapi` starts once `loader` finishes, serving:
  - `http://localhost:5000/collections/flaeche_geo/items?f=jsonfg`
  - `http://localhost:5000/collections/waldabstand_geo/items?f=jsonfg`
  - `http://localhost:5000/collections/mainroads/items?f=jsonfg`
  - `http://localhost:5000/collections/buildinglines/items?f=jsonfg`

Compare against ili2ogc's own reference output:

```bash
curl -s "http://localhost:5000/collections/flaeche_geo/items?f=jsonfg" | python3 -m json.tool
curl -s "http://localhost:5000/collections/waldabstand_geo/items?f=jsonfg" | python3 -m json.tool
curl -s "http://localhost:5000/collections/mainroads/items?f=jsonfg" | python3 -m json.tool
curl -s "http://localhost:5000/collections/buildinglines/items?f=jsonfg" | python3 -m json.tool
python3 compare.py   # checks shared attribute values match, for all 4 collections
```

(Each pygeoapi collection is a base class - directly for `mainroads`
(its base table already has everything, `roadsegment`), or via a thin
`loader/post_load_*.sql` convenience view for the other three, adding
back the `id`/geometry a bare `VIEW` doesn't carry, or linearizing curved
geometry for `buildinglines` - rather than the auto-generated VIEW
verbatim; see [`data/NOTICE.md`](data/NOTICE.md) for why per model. The
attribute VALUES for the real objects should match across both outputs;
each `data/*.jsonfg.json` is that model's own VIEW projection.)

## What's committed vs. downloaded at runtime

| Artifact | Committed? |
|---|---|
| `models/*.ili` (base + derived VIEWs) | yes - this project's own artifacts |
| `data/*.xtf` + their `.jsonfg.json` (not `*.materialized.xtf`) | yes - reference outputs |
| `data/buildingline_sample_source.xtf` | yes - a curated sample, too large to reproduce by re-downloading a subset (see `data/NOTICE.md`) |
| Other real source files | no - downloaded by `loader`, stable URLs in `data/NOTICE.md` |

## Extending

4 models prove the pipeline (2 plain Projections with different geometry
shapes, a JOIN OF, and a Projection with real curved geometry); more
derived models (federal + cantonal, 27 verified in the main repo) will be
added incrementally and the full set packaged as a release ZIP asset (not
committed to the tree) - see `docs/example-repo-pygeoapi-idea.md` in the
main `ili2ogc` repo for the planned scope.
