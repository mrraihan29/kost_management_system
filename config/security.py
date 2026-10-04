"""
config/security.py — Modul utilitas keamanan terpusat.

Berisi:
- Rate limiting berbasis IP (untuk PIN brute-force protection)
- Protected media file serving (mencegah akses publik ke file sensitif)
- Audit logging helpers
"""

import logging
import os

from django.conf import settings
from django.core.cache import cache
from django.http import FileResponse, Http404, HttpResponseForbidden

security_logger = logging.getLogger('security')


# ──────────────────────────────────────────────
# SEC-01: IP-Based Rate Limiting (PIN & Forms)
# ──────────────────────────────────────────────

def get_client_ip(request):
    """
    Ambil IP address klien dengan mempertimbangkan proxy/load balancer.
    Mendukung header X-Forwarded-For (Cloudflare, Nginx, dll).
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # Ambil IP pertama (client asli) dari chain
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
    return ip


def check_rate_limit(request, key_prefix='pin_attempt', max_attempts=5, window=900):
    """
    Periksa apakah IP sudah melebihi batas percobaan.

    Args:
        request: HttpRequest
        key_prefix: Prefix cache key (untuk membedakan jenis rate limit)
        max_attempts: Maksimum percobaan dalam window
        window: Jendela waktu dalam detik (default: 900 = 15 menit)

    Returns:
        tuple: (is_blocked: bool, attempts_used: int, retry_after_seconds: int)
    """
    ip = get_client_ip(request)
    cache_key = f"ratelimit:{key_prefix}:{ip}"

    attempts = cache.get(cache_key, 0)
    if attempts >= max_attempts:
        # Hitung sisa waktu blokir (TTL dari cache key)
        ttl = cache.ttl(cache_key) if hasattr(cache, 'ttl') else window
        return True, attempts, ttl

    return False, attempts, 0


def record_failed_attempt(request, key_prefix='pin_attempt', window=900):
    """
    Catat percobaan gagal ke cache. Increment counter.

    Args:
        request: HttpRequest
        key_prefix: Prefix cache key
        window: Jendela waktu dalam detik
    """
    ip = get_client_ip(request)
    cache_key = f"ratelimit:{key_prefix}:{ip}"

    attempts = cache.get(cache_key, 0)
    cache.set(cache_key, attempts + 1, window)

    # Log percobaan gagal untuk monitoring
    security_logger.warning(
        "Failed %s from IP %s (attempt #%d)",
        key_prefix, ip, attempts + 1
    )


def reset_rate_limit(request, key_prefix='pin_attempt'):
    """
    Reset counter setelah berhasil (opsional, agar user yang berhasil login
    tidak terkena penalty dari percobaan sebelumnya).
    """
    ip = get_client_ip(request)
    cache_key = f"ratelimit:{key_prefix}:{ip}"
    cache.delete(cache_key)


# ──────────────────────────────────────────────
# SEC-06: Protected Media File Serving
# ──────────────────────────────────────────────

# Kategori akses pada folder media
MEDIA_ACCESS_RULES = {
    'ktp_private': 'staff_only',        # KTP hanya untuk admin/staff
    'operation_costs': 'staff_only',    # Nota operasional hanya admin/staff
    'payment_proofs': 'authenticated',  # Staff ATAU penghuni dengan sesi valid
    'maintenance_tickets': 'authenticated',  # Staff ATAU penghuni dengan sesi valid
}


def serve_protected_media(request, path):
    """
    View untuk melayani file media dengan autentikasi.
    Menggantikan static(MEDIA_URL) yang terbuka publik.

    Aturan akses:
    - ktp_private/      → Hanya staff yang login
    - operation_costs/  → Hanya staff yang login
    - payment_proofs/   → Staff ATAU penghuni dengan sesi PIN valid
    - maintenance_tickets/ → Staff ATAU penghuni dengan sesi PIN valid
    """
    # Sanitasi path: cegah directory traversal
    # os.path.normpath akan menormalisasi ../ menjadi path absolut
    clean_path = os.path.normpath(path)
    if clean_path.startswith('..') or clean_path.startswith('/') or ':' in clean_path:
        security_logger.warning(
            "Path traversal attempt blocked: %s (IP: %s)",
            path, get_client_ip(request)
        )
        raise Http404

    file_path = os.path.join(settings.MEDIA_ROOT, clean_path)

    # Pastikan path hasil join masih di dalam MEDIA_ROOT
    real_file_path = os.path.realpath(file_path)
    real_media_root = os.path.realpath(settings.MEDIA_ROOT)
    if not real_file_path.startswith(real_media_root):
        security_logger.warning(
            "Path traversal attempt (realpath) blocked: %s (IP: %s)",
            path, get_client_ip(request)
        )
        raise Http404

    if not os.path.isfile(real_file_path):
        raise Http404

    # Tentukan level akses berdasarkan folder
    folder = clean_path.split(os.sep)[0] if os.sep in clean_path else clean_path.split('/')[0]
    access_rule = MEDIA_ACCESS_RULES.get(folder, 'staff_only')  # Default: staff only

    is_staff = request.user.is_authenticated and request.user.is_staff
    has_session = bool(request.session.get('verified_contract_id'))

    if access_rule == 'staff_only':
        if not is_staff:
            security_logger.warning(
                "Unauthorized media access attempt: %s (IP: %s, user: %s)",
                path, get_client_ip(request),
                request.user.username if request.user.is_authenticated else 'anonymous'
            )
            return HttpResponseForbidden('Akses ditolak.')
    elif access_rule == 'authenticated':
        if not is_staff and not has_session:
            security_logger.warning(
                "Unauthorized media access attempt: %s (IP: %s)",
                path, get_client_ip(request)
            )
            return HttpResponseForbidden('Akses ditolak.')

    # Serve file dengan content type yang tepat
    response = FileResponse(open(real_file_path, 'rb'))

    # Security headers pada response file
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'

    return response


# ──────────────────────────────────────────────
# SEC-12: Audit Logging Helpers
# ──────────────────────────────────────────────

def log_action(request, action, target, detail=''):
    """
    Catat aksi penting untuk audit trail.

    Args:
        request: HttpRequest (untuk IP dan user)
        action: Jenis aksi (e.g., 'PAYMENT_APPROVED', 'TENANT_DELETED')
        target: Objek terkait (string representasi)
        detail: Informasi tambahan
    """
    ip = get_client_ip(request)
    user = request.user.username if request.user.is_authenticated else 'anonymous'

    security_logger.info(
        "AUDIT | user=%s | ip=%s | action=%s | target=%s | detail=%s",
        user, ip, action, target, detail
    )


# ──────────────────────────────────────────────
# B-01: Location Access Helpers (DRY)
# ──────────────────────────────────────────────

def get_user_location(user):
    """
    Ambil assigned_location dari user.
    Returns KostLocation instance atau None.
    """
    if user.is_superuser:
        return None  # Superuser = akses global
    if hasattr(user, 'admin_profile') and user.admin_profile.assigned_location:
        return user.admin_profile.assigned_location
    return None


def filter_by_location(queryset, user, location_field='kost_location'):
    """
    Filter queryset berdasarkan lokasi user.
    Superuser → tanpa filter. Admin biasa → filter ke lokasinya.
    Admin tanpa lokasi → empty queryset.

    Args:
        queryset: Django QuerySet
        user: User instance
        location_field: Nama field/lookup ke KostLocation (e.g., 'kost_location',
                       'contract__room__kost_location', 'room__kost_location')

    Returns:
        Filtered QuerySet
    """
    if user.is_superuser:
        return queryset
    location = get_user_location(user)
    if location:
        return queryset.filter(**{location_field: location})
    return queryset.none()
