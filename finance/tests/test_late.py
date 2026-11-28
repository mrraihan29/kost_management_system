"""Tests for daily late-invoice marking, read-only page loads, and ADR 0002 (EKM-24)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings as django_settings
from django.core.management import call_command
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.models import KostLocation, Room
from finance.billing import (
    issue,
    issue_due,
    preview,
    room_requires_meter,
    tenant_visible_invoices,
)
from finance.models import Invoice
from tenants.models import Tenant, TenantContract
from users.models import AdminProfile, User


def _make_contract(
    *,
    location_name: str,
    billing_mode: str,
    bills_electricity: bool,
    room_number: str = "R-01",
    start_date: date = date(2026, 4, 10),
) -> tuple[KostLocation, TenantContract]:
    loc = KostLocation.objects.create(
        name=location_name,
        address="Jl. Test",
        billing_mode=billing_mode,
        bills_electricity=bills_electricity,
    )
    room = Room.objects.create(
        kost_location=loc,
        room_number=room_number,
        price_monthly=Decimal("1500000.00"),
    )
    tenant = Tenant.objects.create(
        full_name=f"Penghuni {room_number}",
        phone_number="08123456789",
        emergency_contact_phone="08129876543",
    )
    contract = TenantContract.objects.create(
        tenant=tenant,
        room=room,
        start_date=start_date,
        monthly_rent_amount=Decimal("1500000.00"),
    )
    return loc, contract


@pytest.mark.django_db
class TestMarkLateInvoicesCommand:
    """manage.py mark_late_invoices marks past-due BELUM_LUNAS without fees."""

    def test_marks_past_due_unpaid_without_fee_and_keeps_due_today(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, contract_overdue = _make_contract(
            location_name="Kost Satu",
            billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value,
            bills_electricity=False,
            room_number="R-01",
        )
        _, contract_today = _make_contract(
            location_name="Kost Dua",
            billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value,
            bills_electricity=False,
            room_number="R-02",
        )
        overdue = Invoice.objects.create(
            contract=contract_overdue,
            billing_period_start=date(2026, 4, 1),
            due_date=date(2026, 4, 11),
            base_rent_amount=Decimal("1500000.00"),
            status="BELUM_LUNAS",
        )
        due_today = Invoice.objects.create(
            contract=contract_today,
            billing_period_start=date(2026, 4, 2),
            due_date=date(2026, 4, 12),
            base_rent_amount=Decimal("1500000.00"),
            status="BELUM_LUNAS",
        )

        # 2026-04-11 17:05 UTC == 2026-04-12 00:05 Asia/Jakarta
        monkeypatch.setattr(
            timezone,
            "now",
            lambda: datetime(2026, 4, 11, 17, 5, tzinfo=UTC),
        )
        out = StringIO()
        call_command("mark_late_invoices", stdout=out)
        assert out.getvalue().strip().splitlines() == [
            "mark_late_invoices date=2026-04-12 updated=1"
        ]

        overdue.refresh_from_db()
        due_today.refresh_from_db()
        assert overdue.status == "TELAT_BAYAR"
        assert overdue.total_amount == Decimal("1500000.00")
        assert due_today.status == "BELUM_LUNAS"

    def test_does_not_change_awaiting_verification_or_paid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, contract_pending = _make_contract(
            location_name="Kost Pending",
            billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value,
            bills_electricity=False,
            room_number="R-03",
        )
        _, contract_paid = _make_contract(
            location_name="Kost Paid",
            billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value,
            bills_electricity=False,
            room_number="R-04",
        )
        pending = Invoice.objects.create(
            contract=contract_pending,
            billing_period_start=date(2026, 3, 1),
            due_date=date(2026, 3, 11),
            base_rent_amount=Decimal("1500000.00"),
            status="MENUNGGU_VERIFIKASI",
        )
        paid = Invoice.objects.create(
            contract=contract_paid,
            billing_period_start=date(2026, 3, 1),
            due_date=date(2026, 3, 11),
            base_rent_amount=Decimal("1500000.00"),
            status="LUNAS",
        )
        monkeypatch.setattr(
            timezone,
            "now",
            lambda: datetime(2026, 4, 15, 0, 5, tzinfo=UTC),
        )
        call_command("mark_late_invoices", stdout=StringIO())
        pending.refresh_from_db()
        paid.refresh_from_db()
        assert pending.status == "MENUNGGU_VERIFIKASI"
        assert paid.status == "LUNAS"


@pytest.mark.django_db
class TestNoPageLoadWritesAndNoNameDetection:
    """Dashboard and invoice_list perform zero UPDATEs; location name drives no billing rule."""

    @pytest.fixture(autouse=True)
    def _plain_staticfiles(self, settings: Any) -> None:
        settings.STORAGES = {
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }

    def test_dashboard_and_invoice_list_perform_no_update_queries(self) -> None:
        loc, contract = _make_contract(
            location_name="Kost Baca",
            billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value,
            bills_electricity=False,
        )
        overdue = Invoice.objects.create(
            contract=contract,
            billing_period_start=date(2025, 1, 1),
            due_date=date(2025, 1, 11),
            base_rent_amount=Decimal("1500000.00"),
            status="BELUM_LUNAS",
        )
        staff = User.objects.create_user(username="staff_ro", password="x", is_staff=True)
        AdminProfile.objects.create(user=staff, assigned_location=loc)
        client = Client()
        client.force_login(staff)

        with CaptureQueriesContext(connection) as ctx:
            assert client.get(reverse("dashboard")).status_code == 200
            assert client.get(reverse("invoice_list")).status_code == 200

        update_queries = [
            q["sql"]
            for q in ctx.captured_queries
            if q["sql"].lstrip().upper().startswith("UPDATE")
            and "DJANGO_SESSION" not in q["sql"].upper()
        ]
        assert update_queries == []
        overdue.refresh_from_db()
        assert overdue.status == "BELUM_LUNAS"

    def test_renaming_location_changes_no_billing_or_meter_behaviour(self) -> None:
        cycle_loc, cycle_contract = _make_contract(
            location_name="Kost Utara",
            billing_mode=KostLocation.BillingMode.PER_ROOM_CYCLE.value,
            bills_electricity=True,
            room_number="U-01",
            start_date=date(2026, 5, 10),
        )
        sim_loc, sim_contract = _make_contract(
            location_name="Kost Selatan",
            billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value,
            bills_electricity=False,
            room_number="S-01",
            start_date=date(2026, 5, 10),
        )

        # Rename so the simultaneous one says "Ancol" and the cycle one does not.
        cycle_loc.name = "Kost Baru"
        cycle_loc.save()
        sim_loc.name = "Kost Ancol Cabang 2"
        sim_loc.save()
        cycle_contract.refresh_from_db()
        sim_contract.refresh_from_db()

        due_created = issue_due(date(2026, 5, 3))
        assert [i.contract for i in due_created] == [cycle_contract]
        assert room_requires_meter(cycle_contract.room) is True
        assert list(tenant_visible_invoices(cycle_contract)) == []

        staff = User.objects.create_user(username="staff_rename", password="x", is_staff=True)
        assert preview(sim_loc, 2026, 5).to_create == [sim_contract]
        sim_created = issue(sim_loc, 2026, 5, by=staff)
        assert len(sim_created) == 1
        assert room_requires_meter(sim_contract.room) is False
        assert list(tenant_visible_invoices(sim_contract)) == sim_created


def test_no_ancol_reference_in_application_code() -> None:
    """ADR 0002 contract step: application code contains zero case-insensitive 'ancol' matches."""
    base = Path(django_settings.BASE_DIR)
    hits: list[str] = []
    for app in ("config", "core", "finance", "tenants", "users"):
        for path in (base / app).rglob("*.py"):
            rel = path.relative_to(base)
            parts = set(rel.parts)
            if (
                "migrations" in parts
                or "tests" in parts
                or path.name == "seed_data.py"
                or path.name == "tests.py"
                or path.name.startswith("test_")
                or path.name.startswith("tests_")
            ):
                continue
            text = path.read_text(encoding="utf-8")
            if "ancol" in text.lower():
                hits.append(rel.as_posix())
    assert hits == []
