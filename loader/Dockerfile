FROM python:3.12-slim

RUN pip install --no-cache-dir psycopg2-binary

COPY load.py post_load.sql /loader/

CMD ["python", "/loader/load.py"]
