FROM python:3.12-slim

RUN pip install --no-cache-dir psycopg2-binary ili2ogc==0.3.1

COPY load.py /loader/

CMD ["python", "/loader/load.py"]
