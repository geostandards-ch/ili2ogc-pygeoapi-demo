# ili2ogc pygeoapi demo

A [pygeoapi](https://pygeoapi.io) instance serving real Swiss geodata,
loaded via [ili2ogc](https://github.com/maxcollombin/ili2ogc), a
pure-Python INTERLIS 2 toolkit.

## Run

The loader installs [`ili2ogc`](https://pypi.org/project/ili2ogc/) from
PyPI; nothing else is needed besides Docker.

```bash
docker compose up --build
```

## How it is built

The loader writes no SQL of its own. For each dataset, `interlis
convert-sql` generates a PostgreSQL schema laid out like ili2db's
(`t_id`, `t_basket`, `t_ili_tid`, the `T_ILI2DB_*` tables), plus, with
`--map-views`, one view per symbology `GRAPHIC` exposing the attributes
its SLD filters test (`FacilityKind.Reference.KindID`, ...).
`interlis convert-sld` writes those SLDs. Each dataset gets its own
PostgreSQL schema, named like its collection. pygeoapi serves features from
the tables and maps from the generated views.

## Collections

| Collection | Dataset ([geocat.ch](https://www.geocat.ch) record) | Data provider |
|---|---|---|
| `richtplanung` | [Richtplanung erneuerbare Energien](https://www.geocat.ch/geonetwork/srv/eng/catalog.search#/metadata/f5c2c313-00bb-43d6-a3a8-7ccb5a099a96) (canton Schaffhausen) | KGK-CGC / [geodienste.ch](https://geodienste.ch) |
| `waldabstandslinien` | [Waldabstandslinien](https://www.geocat.ch/geonetwork/srv/eng/catalog.search#/metadata/a81f0dc0-a795-4035-822c-4c3bf36e0916) (canton Glarus) | KGK-CGC / [geodienste.ch](https://geodienste.ch) |
| `mainroads` | [Main roads network](https://www.geocat.ch/geonetwork/srv/eng/catalog.search#/metadata/c1333de6-fb91-4b0b-be95-8eab89b05358) | FEDRO |
| `buildinglines` | [Building lines for motorways](https://www.geocat.ch/geonetwork/srv/eng/catalog.search#/metadata/fce3b347-cc58-4b29-bb87-a35eed4487ea) (30-object sample) | FEDRO |
| `uebertragungsleitungen` | [Electricity Transmission Lines sectoral plan](https://www.geocat.ch/geonetwork/srv/eng/catalog.search#/metadata/e1134feb-55d7-4b44-8e13-125e983b259b) | SFOE |
| `asyl` | [Sectoral plan for Asylum (SPA)](https://www.geocat.ch/geonetwork/srv/eng/catalog.search#/metadata/23a9027d-37a1-4ba4-b529-54c658540914) | SEM |

```bash
curl "http://localhost:5000/collections/richtplanung/items?f=jsonfg"
curl "http://localhost:5000/collections/waldabstandslinien/map?bbox=9.0544,47.0937,9.1785,47.1164" -o map.png
curl "http://localhost:5000/collections/waldabstandslinien/map?bbox=2722621,1217159,2732023,1219842&bbox-crs=http://www.opengis.net/def/crs/EPSG/0/2056" -o map.png
```

All collections also serve OGC API - Maps (`/map`). Two things
to get right when requesting one:

- A `bbox` in EPSG:2056 (Swiss metres) must be paired with
  `bbox-crs=http://www.opengis.net/def/crs/EPSG/0/2056`, or the server
  reads the numbers as degrees. Without `bbox-crs`, use CRS84 degrees.
- Ask for a `bbox` close to the collection's own advertised
  `extent.spatial.bbox` (`/collections/{id}`). These datasets are small
  — `waldabstandslinien` covers about 9 km — so a Switzerland-wide `bbox`
  renders their lines below one pixel and the image comes back blank.

## License

Code: MIT (see `LICENSE`), like pygeoapi itself. Data: © the data providers listed above, open use with
mandatory source attribution ([opendata.swiss BY](https://opendata.swiss/en/terms-of-use/#terms_by)).
