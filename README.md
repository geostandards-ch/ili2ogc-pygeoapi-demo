# ili2ogc pygeoapi demo

A [pygeoapi](https://pygeoapi.io) instance serving Swiss geodata straight
from their INTERLIS transfers, converted by
[ili2ogc](https://github.com/geostandards-ch/ili2ogc): OGC API - Features
(GeoJSON, JSON-FG) and OGC API - Maps, styled by the INTERLIS symbology.

```bash
docker compose up --build
```

Then open <http://localhost:5000>. Each dataset is a directory under
`collections/` (its INTERLIS VIEWs, symbology and signs); the official
models they import are fetched from the INTERLIS model repositories.

## Data

| Collections | Dataset ([geocat.ch](https://www.geocat.ch) record) | Data provider |
|---|---|---|
| `richtplanung`, `richtplanung_punkte` | [Richtplanung erneuerbare Energien](https://www.geocat.ch/geonetwork/srv/eng/catalog.search#/metadata/f5c2c313-00bb-43d6-a3a8-7ccb5a099a96) (canton Schaffhausen) | KGK-CGC / [geodienste.ch](https://geodienste.ch) |
| `waldabstandslinien` | [Waldabstandslinien](https://www.geocat.ch/geonetwork/srv/eng/catalog.search#/metadata/a81f0dc0-a795-4035-822c-4c3bf36e0916) (canton Glarus) | KGK-CGC / [geodienste.ch](https://geodienste.ch) |
| `mainroads` | [Main roads network](https://www.geocat.ch/geonetwork/srv/eng/catalog.search#/metadata/c1333de6-fb91-4b0b-be95-8eab89b05358) | FEDRO |
| `buildinglines` | [Building lines for motorways](https://www.geocat.ch/geonetwork/srv/eng/catalog.search#/metadata/fce3b347-cc58-4b29-bb87-a35eed4487ea) (sample) | FEDRO |
| `uebertragungsleitungen`, `_linien`, `_punkte` | [Electricity Transmission Lines sectoral plan](https://www.geocat.ch/geonetwork/srv/eng/catalog.search#/metadata/e1134feb-55d7-4b44-8e13-125e983b259b) | SFOE |
| `asyl` | [Sectoral plan for Asylum](https://www.geocat.ch/geonetwork/srv/eng/catalog.search#/metadata/23a9027d-37a1-4ba4-b529-54c658540914) | SEM |
| `militaer`, `militaer_punkte` | [Sectoral Plan Military](https://www.geocat.ch/geonetwork/srv/eng/catalog.search#/metadata/5263bc47-8723-4c02-988a-4ae0d425099c) ¹ | armasuisse / DDPS |

¹ The published transfer carries no coordinates; the one used here is
completed with the geometries of the dataset's own File Geodatabase
export, matched by TID.

## License

Code: MIT (see `LICENSE.md`), the license of [pygeoapi](https://github.com/geopython/pygeoapi).

Data: © the data providers above. Open use; the source must be provided
([opendata.swiss BY](https://opendata.swiss/en/terms-of-use/#terms_by)).
