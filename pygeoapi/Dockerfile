FROM geopython/pygeoapi:latest

RUN /venv/bin/python3 -m pip install --no-cache-dir psycopg2-binary pygeoapi-plugins

# JSON-FG formatter of this demo: pygeoapi_plugins' one, with `featureType` = the VIEW a collection serves, not
# `OGRGeoJSON`. Put next to the installed packages so the configuration can name it as `ili2ogc_jsonfg.JSONFG`.
COPY ili2ogc_jsonfg.py /tmp/ili2ogc_jsonfg.py
RUN cp /tmp/ili2ogc_jsonfg.py "$(/venv/bin/python3 -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')/" \
 && rm /tmp/ili2ogc_jsonfg.py

COPY pygeoapi-config.yml /pygeoapi/local.config.yml
