#!/bin/sh
# entrypoint.sh — SEC-16: Separate migration from application server
#
# Jalankan migrasi database SEKALI sebelum start Gunicorn.
# Jika ada multiple replicas, hanya replica pertama yang run migrate.
# Gunicorn akan retry koneksi jika DB belum ready.

set -e

echo "=== Running database migrations ==="
python manage.py migrate --noinput

echo "=== Starting application server ==="
exec "$@"
