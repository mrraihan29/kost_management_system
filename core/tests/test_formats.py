"""Tests for Indonesian Rupiah and date/month formatting (EKM-18, R-009)."""

import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django.template import Context, Template
from django.test import Client
from django.urls import reverse
from openpyxl import load_workbook

from core.formats import month_name, rupiah
from core.models import KostLocation
from users.models import User


class TestRupiahAndMonthHelpers:
    """Unit tests for core.formats.rupiah and core.formats.month_name."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (1850000, "Rp 1.850.000"),
            (Decimal("1850000.00"), "Rp 1.850.000"),
            (Decimal("1850000.60"), "Rp 1.850.001"),
            (-50000, "\u2212Rp 50.000"),
            (Decimal("-1250000"), "\u2212Rp 1.250.000"),
            (0, "Rp 0"),
            (Decimal("-0.00"), "Rp 0"),
            (None, "Rp 0"),
            ("", "Rp 0"),
        ],
    )
    def test_rupiah_formats_whole_amounts(
        self, raw: Decimal | int | float | str | None, expected: str
    ) -> None:
        assert rupiah(raw) == expected

    def test_month_name_returns_indonesian_months(self) -> None:
        assert [month_name(m) for m in range(1, 13)] == [
            "Januari",
            "Februari",
            "Maret",
            "April",
            "Mei",
            "Juni",
            "Juli",
            "Agustus",
            "September",
            "Oktober",
            "November",
            "Desember",
        ]

    @pytest.mark.parametrize("bad_month", [0, 13, -1])
    def test_month_name_rejects_out_of_range(self, bad_month: int) -> None:
        with pytest.raises(ValueError):
            month_name(bad_month)


class TestTemplateFormatting:
    """Template filters and Django id-locale date formats."""

    def test_rupiah_filter_renders_positive_and_negative(self) -> None:
        tpl = Template("{% load finance_extras %}{{ pos|rupiah }} | {{ neg|rupiah }}")
        rendered = tpl.render(Context({"pos": 1850000, "neg": -50000}))
        assert rendered == "Rp 1.850.000 | \u2212Rp 50.000"

    def test_indonesian_date_formats(self) -> None:
        tpl = Template('{{ d|date:"j F Y" }} | {{ d|date:"j M" }} | {{ d|date:"F Y" }}')
        rendered = tpl.render(Context({"d": datetime.date(2026, 11, 14)}))
        assert rendered == "14 November 2026 | 14 Nov | November 2026"


@pytest.mark.django_db
class TestReportAndExportIndonesianFormatting:
    """Finance report, chart axis callbacks, and Excel export use Indonesian formatting."""

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
        self.owner = User.objects.create_superuser(username="owner_fmt", email="", password="x")
        self.client = Client()
        self.client.force_login(self.owner)

    def test_finance_report_has_indonesian_months_and_chart_rupiah(self) -> None:
        resp = self.client.get(reverse("finance_report"))
        assert resp.status_code == 200
        body = resp.content.decode("utf-8")
        assert "Januari" in body
        assert "Oktober" in body
        assert "Desember" in body
        for eng in ("January", "February", "March", "May", "August", "October", "December"):
            assert eng not in body
        assert "formatRupiah" in body

    def test_export_finance_excel_uses_indonesian_months(self, tmp_path: Path) -> None:
        resp = self.client.get(reverse("export_finance_excel"))
        assert resp.status_code == 200
        xlsx = tmp_path / "report.xlsx"
        xlsx.write_bytes(resp.content)
        wb = load_workbook(xlsx)
        ws = wb["Ringkasan Bulanan"]
        months = [ws.cell(row=r, column=1).value for r in range(2, 14)]
        assert months == [month_name(m) for m in range(1, 13)]


def test_no_strftime_percent_b_in_application_code() -> None:
    """Guardrail (EKM-18): no strftime('%B') remains in application code."""
    repo_root = Path(__file__).resolve().parents[2]
    offenders: list[str] = []
    for app in ("core", "finance", "tenants", "users"):
        for py_file in (repo_root / app).rglob("*.py"):
            rel = py_file.relative_to(repo_root).as_posix()
            if "/migrations/" in rel or "/tests/" in rel:
                continue
            text = py_file.read_text(encoding="utf-8")
            if 'strftime("%B' in text or "strftime('%B" in text:
                offenders.append(rel)
    assert offenders == [], f"strftime('%B') still present in: {offenders}"
