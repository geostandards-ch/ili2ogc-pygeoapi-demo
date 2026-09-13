# ili2ogc pygeoapi demo

A [pygeoapi](https://pygeoapi.io) instance serving real Swiss geodata,
loaded via [ili2ogc](https://github.com/maxcollombin/ili2ogc), a
pure-Python INTERLIS 2 toolkit.

## Run

Requires a local checkout of `ili2ogc` as a sibling directory
(`../interlis-runtime`).

```bash
docker compose up --build
```

## Collections

| Collection | Dataset |
|---|---|
| `flaeche_geo` | Renewable energy planning areas (Schaffhausen) |
| `waldabstand_geo` | Forest-distance lines (Glarus) |
| `mainroads` | Main road segments |
| `buildinglines` | Building restriction lines along motorways |
| `uebertragungsleitungen` | Electricity transmission planning corridors/areas |

```bash
curl "http://localhost:5000/collections/flaeche_geo/items?f=jsonfg"
curl "http://localhost:5000/collections/waldabstand_geo/map?bbox=2590000,1210000,2900000,1400000&bbox-crs=http://www.opengis.net/def/crs/EPSG/0/2056" -o map.png
```

`waldabstand_geo`, `mainroads`, `buildinglines`, and
`uebertragungsleitungen` also serve OGC API - Maps (`/map`). Data is in
EPSG:2056 (Swiss coordinates) — a `bbox` in EPSG:2056 must be paired with
`bbox-crs=http://www.opengis.net/def/crs/EPSG/0/2056`, or the server will
misread it as degrees.

## License

MIT — see `data/NOTICE.md` for data source attribution.
