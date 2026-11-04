FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/data HOME=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends nginx supervisor \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home researcher \
    && mkdir -p /data /app /tmp/nginx \
    && chown -R researcher:researcher /data /app /tmp/nginx
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY --from=frontend /build/dist /app/static
COPY deploy/nginx.conf /app/nginx.conf
COPY deploy/supervisord.conf /app/supervisord.conf
USER researcher
EXPOSE 6001 6002
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6001/api/health'); urllib.request.urlopen('http://127.0.0.1:6002/')"
CMD ["supervisord", "-c", "/app/supervisord.conf"]
