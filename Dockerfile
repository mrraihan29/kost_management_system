# 1. Gunakan Python 3.11 versi ringan (Slim)
FROM python:3.11-slim

# 2. Set environment variables agar Python tidak membuat file .pyc
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Buat folder kerja di dalam container
WORKDIR /app

# 4. Install dependencies sistem (untuk Postgres)
RUN apt-get update && apt-get install -y libpq-dev gcc

# 5. Copy requirements dan install
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy seluruh kode proyek ke dalam container
COPY . /app/

# 7. Kumpulkan file static (CSS/JS) ke satu folder
RUN python manage.py collectstatic --noinput

# 8. Perintah saat container jalan: Jalankan Gunicorn
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]