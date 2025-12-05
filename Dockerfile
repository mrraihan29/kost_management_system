# 1. Gunakan Python 3.11 versi ringan (Slim)
FROM python:3.11-slim

# 2. Set environment variables agar Python tidak membuat file .pyc
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Buat folder kerja di dalam container
WORKDIR /app

# 4. Install dependencies sistem (untuk Postgres) + curl buat healthcheck
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
 && rm -rf /var/lib/apt/lists/*

# 5. Copy requirements dan install
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy seluruh kode proyek ke dalam container
COPY . /app/

# 7. Kumpulkan file static (CSS/JS) ke satu folder
RUN python manage.py collectstatic --noinput

# 8. Healthcheck bawaan Docker (Coolify otomatis baca)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health/ || exit 1

# 9. Jalankan Gunicorn
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]