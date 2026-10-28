FROM python:3.12-slim

WORKDIR /app

COPY qoder/wengu/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY qoder/wengu/ ./
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    SEEKDB_HOST=seekdb \
    SEEKDB_PORT=2881 \
    SEEKDB_USER=root \
    SEEKDB_PASSWORD= \
    SEEKDB_DATABASE=wengu \
    EMBED_PROVIDER=hash \
    EMBED_DIM=1024

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
