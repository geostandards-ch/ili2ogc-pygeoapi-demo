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
curl "http://localhost:5000/collections/waldabstand_geo/map?bbox=9.0544,47.0937,9.1785,47.1164" -o map.png
curl "http://localhost:5000/collections/waldabstand_geo/map?bbox=2722621,1217159,2732023,1219842&bbox-crs=http://www.opengis.net/def/crs/EPSG/0/2056" -o map.png
```

`waldabstand_geo`, `mainroads`, `buildinglines`, and
`uebertragungsleitungen` also serve OGC API - Maps (`/map`). Two things
to get right when requesting one:

- A `bbox` in EPSG:2056 (Swiss metres) must be paired with
  `bbox-crs=http://www.opengis.net/def/crs/EPSG/0/2056`, or the server
  reads the numbers as degrees. Without `bbox-crs`, use CRS84 degrees.
- Ask for a `bbox` close to the collection's own advertised
  `extent.spatial.bbox` (`/collections/{id}`). These datasets are small
  — `waldabstand_geo` covers about 9 km — so a Switzerland-wide `bbox`
  renders their lines below one pixel and the image comes back blank.

## License

MIT — see `data/NOTICE.md` for data source attribution.
