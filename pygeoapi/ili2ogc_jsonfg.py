"""JSON-FG output whose `featureType` is the INTERLIS VIEW a collection serves.

pygeoapi_plugins' JSON-FG formatter writes the GDAL provider default, `OGRGeoJSON`. Each collection of this demo is
one VIEW of its views model, published as the SQL table of the same name, so that name (the provider's `table`, or
`feature_type` when given) is the feature type `ili2ogc convert-jsonfg` and the CartoSym `dataLayer.id` of the
collection's GRAPHIC use.
"""

import json

from pygeoapi.util import to_json
from pygeoapi_plugins.formatter.jsonfg import JSONFGFormatter


class JSONFG(JSONFGFormatter):
    """The pygeoapi_plugins JSON-FG formatter, with `featureType` set from the provider definition."""

    def write(self, options: dict = {}, data: dict | None = {}) -> str:
        """Write JSON-FG, naming the collection's feature type on the document and on every feature."""
        content = super().write(options=options, data=data)
        provider = options.get("provider_def") or {}
        feature_type = provider.get("feature_type") or provider.get("table")
        if not content or not feature_type:
            return content
        document = json.loads(content)
        document["featureType"] = feature_type
        for feature in document.get("features", []):
            feature["featureType"] = feature_type
        return to_json(document)
