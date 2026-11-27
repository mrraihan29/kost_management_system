# 1. Python ringan (slim).
FROM python:3.14-slim

# 2. uv dari image resminya, versi dipatok
COPY --from=ghcr.io/astral-sh/uv:0.7.7 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# 3. Dependensi sistem (Postgres) + curl untuk healthcheck
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
 && rm -rf /var/lib/apt/lists/*

# 4. Dependensi Python dari uv.lock (tanpa grup dev), di-cache terpisah dari kode
COPY pyproject.toml uv.lock .python-version /app/
RUN uv sync --frozen --no-dev

# 5. Kode proyek (.dockerignore menyaring .env, database lokal, media, .venv)
COPY . /app/

# 6. Kumpulkan file static
RUN python manage.py collectstatic --noinput

# 7. Direktori logs (SEC-12: audit logging; pindah ke stdout di EKM-35)
RUN mkdir -p /app/logs

# 8. Healthcheck bawaan Docker (Coolify otomatis baca)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health/ || exit 1

# 9. SEC-16: migrasi sekali di entrypoint, lalu Gunicorn (non-root user)
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh \
 && useradd --create-home --shell /bin/sh appuser \
 && mkdir -p /app/media \
 && chown -R appuser:appuser /app/logs /app/staticfiles /app/media
USER appuser
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
