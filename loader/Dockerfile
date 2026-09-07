FROM python:3.12-slim

RUN pip install --no-cache-dir psycopg2-binary

COPY load.py post_load_richtplanung.sql post_load_waldabstandslinien.sql post_load_buildinglinesformotorways.sql /loader/

CMD ["python", "/loader/load.py"]
