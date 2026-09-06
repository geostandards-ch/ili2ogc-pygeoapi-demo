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

It also shows `interlis write-xtf`, materializing a VIEW as a standalone
`.xtf` transfer in its own right.

## Models

- [`RichtplanungErneuerbareEnergien_V1`](https://models.geo.admin.ch/BFE/)
  (BFE) - renewable-energy spatial planning, real data for canton
  Schaffhausen. `view_flaeche` (`RichtplanungErneuerbareEnergien_V1_d_01.ili`)
  is a plain `PROJECTION OF` a single class.
- [`Waldabstandslinien_V1_2`](https://models.geo.admin.ch/BAFU/) (BAFU) -
  forest-distance lines, real data for canton Glarus. `view_waldabstand_linie`
  (`Waldabstandslinien_V1_2_d.ili`) is a `JOIN OF Waldabstand_Linie, Typ` -
  unlike the Richtplanung Projection, its own `ATTRIBUTE` block maps the
  geometry through directly, so `convert-sql`'s `CREATE VIEW` already carries
  a real geometry column (no base-table workaround needed for this one).

Both already verified end-to-end (SQL and JSON-FG identical) in the main
`ili2ogc` repo. See [`data/NOTICE.md`](data/NOTICE.md) for full provenance
and the one documented gap this demo worked around (now fixed upstream).

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

- `loader` downloads both real source `.xtf` files, builds the PostGIS
  schema for each model (`interlis convert-sql`), loads them, and
  materializes each VIEW as a `.xtf` (`interlis write-xtf`), then exits.
- `pygeoapi` starts once `loader` finishes, serving:
  - `http://localhost:5000/collections/flaeche_geo/items?f=jsonfg`
  - `http://localhost:5000/collections/waldabstand_geo/items?f=jsonfg`

Compare against ili2ogc's own reference output:

```bash
curl -s "http://localhost:5000/collections/flaeche_geo/items?f=jsonfg" | python3 -m json.tool
curl -s "http://localhost:5000/collections/waldabstand_geo/items?f=jsonfg" | python3 -m json.tool
python3 compare.py   # checks shared attribute values match, for both collections
```

(Both collections are hand-written convenience views over the base
class(es) rather than the auto-generated VIEW verbatim - see
[`data/NOTICE.md`](data/NOTICE.md) for why. The attribute VALUES for the
real objects should match across both outputs; `data/view_flaeche.jsonfg.json`/
`data/view_waldabstand_linie.jsonfg.json` are each VIEW's own projection.)

## What's committed vs. downloaded at runtime

| Artifact | Committed? |
|---|---|
| `models/*.ili` (base + derived VIEWs) | yes - this project's own artifacts |
| `data/view_flaeche.xtf`, `data/view_waldabstand_linie.xtf` + their `.jsonfg.json` | yes - reference outputs |
| Real source `.xtf` files | no - downloaded by `loader`, stable URLs in `data/NOTICE.md` |

## Extending

2 models prove the pipeline (a plain Projection and a JOIN OF); more derived
models (federal + cantonal, 27 verified in the main repo) will be added
incrementally and the full set packaged as a release ZIP asset (not
committed to the tree) - see `docs/example-repo-pygeoapi-idea.md` in the
main `ili2ogc` repo for the planned scope.
