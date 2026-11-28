"""
URL configuration for config project.

Security hardened:
- SEC-05: Health check endpoint hides DB error details
- SEC-06: Media files served via protected view with authentication
- SEC-07: Admin panel URL obscured
"""

import logging

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import JsonResponse
from django.urls import include, path, re_path

from config.security import serve_protected_media
from core.views import home

security_logger = logging.getLogger("security")


# SEC-05: Health check — JANGAN bocorkan detail error database
def health_check(request):
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok", "database": "connected"})
    except Exception:
        # Log detail error untuk internal monitoring, tapi jangan kirim ke client
        security_logger.error("Health check: database connection failed", exc_info=True)
        return JsonResponse({"status": "error", "database": "unavailable"}, status=503)


urlpatterns = [
    # SEC-07: Admin panel di path yang tidak obvious
    path("sekretariat-evykost/", admin.site.urls),
    path("health/", health_check, name="health_check"),
    path("", home, name="home"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            template_name="auth/login.html", extra_context={"hide_sidebar": True}
        ),
        name="login",
    ),
    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(next_page="/accounts/login/"),
        name="logout",
    ),
    path("", include("finance.urls")),
    path("staff/", include("core.urls")),
    path("staff/tenants/", include("tenants.urls")),
    path("management/", include("users.urls")),
    path(
        "accounts/password_change/",
        auth_views.PasswordChangeView.as_view(template_name="auth/password_change.html"),
        name="password_change",
    ),
    path(
        "accounts/password_change/done/",
        auth_views.PasswordChangeDoneView.as_view(template_name="auth/password_change_done.html"),
        name="password_change_done",
    ),
    # SEC-06: Media files dilayani melalui protected view (bukan static serving)
    re_path(r"^media/(?P<path>.+)$", serve_protected_media, name="protected_media"),
]

# JANGAN gunakan static(MEDIA_URL) — semua media melalui view yang authenticated
