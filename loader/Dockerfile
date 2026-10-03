FROM python:3.12-slim

RUN pip install --no-cache-dir psycopg2-binary ili2ogc==0.1.4

COPY load.py post_load_richtplanung.sql post_load_waldabstandslinien.sql post_load_buildinglinesformotorways.sql post_load_sachplan_uebertragungsleitungen.sql post_load_sachplan_asyl.sql /loader/

CMD ["python", "/loader/load.py"]
