FROM geopython/pygeoapi:latest

RUN /venv/bin/python3 -m pip install --no-cache-dir psycopg2-binary pygeoapi-plugins

COPY pygeoapi-config.yml /pygeoapi/local.config.yml
