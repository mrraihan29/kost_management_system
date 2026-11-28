"""Tests for Tailwind CSS pipeline, Plat Nomor shell, and role navigation (EKM-17)."""

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings as django_settings
from django.test import Client
from django.urls import reverse

from core.models import KostLocation
from core.navigation import nav_items_for
from users.models import AdminProfile, User


@pytest.mark.django_db
class TestNavigation:
    """Role-based navigation items and active matching."""

    def setup_method(self) -> None:
        self.location = KostLocation.objects.create(
            name="Kost Ancol", address="Jl A", electricity_rate_per_kwh=Decimal("1500")
        )
        self.owner = User.objects.create_superuser(username="owner_nav", email="", password="x")
        self.staff = User.objects.create_user(username="staff_nav", password="x", is_staff=True)
        AdminProfile.objects.create(user=self.staff, assigned_location=self.location)

    def test_staff_gets_five_items_and_owner_gets_eight_excluding_styleguide(self) -> None:
        staff_items = nav_items_for(self.staff, "dashboard")
        assert [item.label for item in staff_items] == [
            "Beranda",
            "Tagihan",
            "Penghuni & Kamar",
            "Pengeluaran",
            "Kerusakan",
        ]
        assert staff_items[0].current is True
        assert all(item.url_name != "styleguide" for item in staff_items)

        owner_items = nav_items_for(self.owner, "staff_list")
        assert [item.label for item in owner_items] == [
            "Beranda",
            "Tagihan",
            "Penghuni & Kamar",
            "Pengeluaran",
            "Kerusakan",
            "Laporan Keuangan",
            "Lokasi",
            "Staff",
        ]
        assert owner_items[-1].current is True
        assert all(item.url_name != "styleguide" for item in owner_items)

    def test_active_item_matches_sub_routes(self) -> None:
        items_inv = nav_items_for(self.staff, "invoice_detail")
        assert next(i for i in items_inv if i.label == "Tagihan").current is True

        items_room = nav_items_for(self.staff, "room_list")
        assert next(i for i in items_room if i.label == "Penghuni & Kamar").current is True


@pytest.mark.django_db
class TestStyleguideAndShell:
    """Styleguide authorization, zero external CDN requests on Plat Nomor pages, and CSS output."""

    @pytest.fixture(autouse=True)
    def _plain_staticfiles(self, settings: Any) -> None:
        settings.STORAGES = {
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }

    def setup_method(self) -> None:
        self.location = KostLocation.objects.create(
            name="Kost Ancol", address="Jl A", electricity_rate_per_kwh=Decimal("1500")
        )
        self.owner = User.objects.create_superuser(username="owner_sg", email="", password="x")
        self.staff = User.objects.create_user(username="staff_sg", password="x", is_staff=True)
        AdminProfile.objects.create(user=self.staff, assigned_location=self.location)

    def test_styleguide_owner_only_shows_all_glazes_and_loads_no_external_hosts(self) -> None:
        url = reverse("styleguide")
        assert Client().get(url).status_code == 302

        staff_client = Client()
        staff_client.force_login(self.staff)
        assert staff_client.get(url).status_code == 404

        owner_client = Client()
        owner_client.force_login(self.owner)
        resp = owner_client.get(url)
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        for glaze in ("g-paid", "g-wait", "g-late", "g-meter", "g-unpaid", "g-empty"):
            assert glaze in body
        assert 'aria-current="page"' not in body  # styleguide is not in nav
        for forbidden_host in (
            "cdn.jsdelivr.net",
            "cdnjs.cloudflare.com",
            "fonts.googleapis.com",
            "fonts.gstatic.com",
        ):
            assert forbidden_host not in body

    def test_shell_navigation_renders_role_count_and_aria_current(self) -> None:
        staff_client = Client()
        staff_client.force_login(self.staff)
        staff_body = staff_client.get(reverse("dashboard")).content.decode("utf-8")
        assert '<nav aria-label="Utama"' in staff_body
        assert 'aria-current="page"' in staff_body
        assert "Laporan Keuangan" not in staff_body
        assert "Kelola Staff" not in staff_body

        owner_client = Client()
        owner_client.force_login(self.owner)
        owner_body = owner_client.get(reverse("dashboard")).content.decode("utf-8")
        assert "Laporan Keuangan" in owner_body
        assert "Lokasi" in owner_body
        assert "Staff" in owner_body

    def test_csp_drops_google_fonts_and_app_css_is_built(self) -> None:
        directives: dict[str, list[str]] = django_settings.CONTENT_SECURITY_POLICY["DIRECTIVES"]
        all_sources = " ".join(src for values in directives.values() for src in values)
        assert "fonts.googleapis.com" not in all_sources
        assert "fonts.gstatic.com" not in all_sources

        app_css = Path(django_settings.BASE_DIR) / "static" / "css" / "app.css"
        assert app_css.is_file()
        css_text = app_css.read_text(encoding="utf-8")
        assert "--color-enamel" in css_text
        assert ".plate" in css_text
