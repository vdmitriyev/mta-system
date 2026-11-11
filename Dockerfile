FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        dos2unix \
        fonts-freefont-ttf \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# The virtual environment is outside of APP_HOME: compose.yml mounts the project folder there
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/mta-system \
    TARGET_SERVER=production \
    WEB_CONCURRENCY=4 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

WORKDIR $APP_HOME

# Dependencies come from pyproject.toml (uv.lock is not part of the project)
COPY pyproject.toml ./
RUN pip install --no-cache-dir uv \
    && uv sync --no-dev --no-cache \
    && rm -f uv.lock

COPY run.py versions.env ./
COPY configs-logging configs-logging
COPY migrations migrations
COPY app app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Files can come from Windows: convert line endings of the entrypoint
RUN dos2unix /usr/local/bin/docker-entrypoint.sh \
    && chmod +x /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p .logs data

# The SQLite database (MTAS_DB_PATH, default data/mta-system.db) and the logs belong on volumes
VOLUME ["/mta-system/data", "/mta-system/.logs"]

# Runs as root: the app starts and stops the service containers through /var/run/docker.sock
EXPOSE 5151
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5151/api/health', timeout=5)"

ENTRYPOINT ["docker-entrypoint.sh"]
# Number of worker processes: WEB_CONCURRENCY. nginx sets the X-Forwarded-* headers.
CMD ["uvicorn", "run:app", "--host", "0.0.0.0", "--port", "5151", "--proxy-headers", "--forwarded-allow-ips", "*"]
