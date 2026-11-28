"""Tests for meter reading gating on Tenant portal and Staff meter form (EKM-23, R-015)."""

import io
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from PIL import Image

from core.models import KostLocation, Room
from finance.billing import (
    invoices_needing_meter,
    room_requires_meter,
    tenant_visible_invoices,
)
from finance.models import ElectricityReading, Invoice, Payment
from finance.portal import SESSION_CONTRACT_KEY
from tenants.models import Tenant, TenantContract
from users.models import AdminProfile, User


def _proof_file() -> SimpleUploadedFile:
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), color="blue").save(buf, format="JPEG")
    return SimpleUploadedFile("proof.jpg", buf.getvalue(), content_type="image/jpeg")


def _make_invoice(
    *,
    location_name: str,
    bills_electricity: bool,
    is_token: bool,
    room_number: str,
    status: str = "BELUM_LUNAS",
    location: KostLocation | None = None,
) -> tuple[KostLocation, TenantContract, Invoice]:
    loc = location or KostLocation.objects.create(
        name=location_name,
        address="Jl. Test",
        billing_mode=(
            KostLocation.BillingMode.PER_ROOM_CYCLE.value
            if bills_electricity
            else KostLocation.BillingMode.SIMULTANEOUS.value
        ),
        bills_electricity=bills_electricity,
        electricity_rate_per_kwh=Decimal("1500.00"),
    )
    room = Room.objects.create(
        kost_location=loc,
        room_number=room_number,
        price_monthly=Decimal("1500000.00"),
        is_token_electricity=is_token,
    )
    tenant = Tenant.objects.create(
        full_name=f"Penghuni {room_number}",
        phone_number="08123456789",
        emergency_contact_phone="08129876543",
    )
    contract = TenantContract.objects.create(
        tenant=tenant,
        room=room,
        start_date=date(2026, 4, 1),
        monthly_rent_amount=Decimal("1500000.00"),
    )
    invoice = Invoice.objects.create(
        contract=contract,
        billing_period_start=date(2026, 4, 1),
        due_date=date(2026, 4, 11),
        base_rent_amount=Decimal("1500000.00"),
        status=status,
    )
    return loc, contract, invoice


@pytest.mark.django_db
class TestMeterGatingQueries:
    """tenant_visible_invoices and invoices_needing_meter implement R-015."""

    def test_metered_room_at_electricity_location_hidden_until_reading_saved(self) -> None:
        loc, contract, inv = _make_invoice(
            location_name="Kost Ancol",
            bills_electricity=True,
            is_token=False,
            room_number="A-101",
        )
        assert room_requires_meter(contract.room) is True
        assert list(tenant_visible_invoices(contract)) == []
        assert list(invoices_needing_meter(loc)) == [inv]

        ElectricityReading.objects.create(
            invoice=inv,
            meter_reading_start=100,
            meter_reading_end=150,
            rate_per_kwh=Decimal("1500.00"),
        )
        inv.refresh_from_db()
        assert inv.total_amount == Decimal("1575000.00")
        assert list(tenant_visible_invoices(contract)) == [inv]
        assert list(invoices_needing_meter(loc)) == []

    def test_token_room_and_non_electricity_location_visible_immediately_and_never_need_meter(
        self,
    ) -> None:
        ancol, token_contract, _ = _make_invoice(
            location_name="Kost Ancol",
            bills_electricity=True,
            is_token=True,
            room_number="A-201",
        )
        kana, kana_contract, _ = _make_invoice(
            location_name="Kost Kana",
            bills_electricity=False,
            is_token=False,
            room_number="K-101",
        )
        assert room_requires_meter(token_contract.room) is False
        assert room_requires_meter(kana_contract.room) is False
        assert tenant_visible_invoices(token_contract).count() == 1
        assert tenant_visible_invoices(kana_contract).count() == 1
        assert list(invoices_needing_meter(ancol)) == []
        assert list(invoices_needing_meter(kana)) == []

    def test_invoices_needing_meter_includes_late_excludes_paid_pending_and_other_locations(
        self,
    ) -> None:
        ancol, _, unpaid = _make_invoice(
            location_name="Kost Ancol",
            bills_electricity=True,
            is_token=False,
            room_number="A-101",
            status="BELUM_LUNAS",
        )
        _, _, late = _make_invoice(
            location_name="Kost Ancol",
            bills_electricity=True,
            is_token=False,
            room_number="A-102",
            status="TELAT_BAYAR",
            location=ancol,
        )
        _make_invoice(
            location_name="Kost Ancol",
            bills_electricity=True,
            is_token=False,
            room_number="A-103",
            status="MENUNGGU_VERIFIKASI",
            location=ancol,
        )
        _make_invoice(
            location_name="Kost Ancol",
            bills_electricity=True,
            is_token=False,
            room_number="A-104",
            status="LUNAS",
            location=ancol,
        )
        _make_invoice(
            location_name="Kost Lain",
            bills_electricity=True,
            is_token=False,
            room_number="L-101",
            status="BELUM_LUNAS",
        )
        assert list(invoices_needing_meter(ancol)) == [unpaid, late]


@pytest.mark.django_db
class TestMeterGatingViews:
    """Portal upload guard and Staff invoice_detail meter section enforce R-015."""

    @pytest.fixture(autouse=True)
    def _isolated_media_and_static(self, settings: Any, tmp_path: Any) -> None:
        settings.MEDIA_ROOT = str(tmp_path)
        settings.STORAGES = {
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }

    def _staff_client(self, loc: KostLocation, username: str) -> Client:
        staff = User.objects.create_user(username=username, password="x", is_staff=True)
        AdminProfile.objects.create(user=staff, assigned_location=loc)
        client = Client()
        client.force_login(staff)
        return client

    def _tenant_client(self, contract: TenantContract) -> Client:
        client = Client()
        session = client.session
        session[SESSION_CONTRACT_KEY] = contract.pk
        session.save()
        return client

    def test_metered_invoice_unpayable_until_reading_then_payable_with_electricity(self) -> None:
        loc, contract, inv = _make_invoice(
            location_name="Kost Ancol",
            bills_electricity=True,
            is_token=False,
            room_number="A-101",
        )
        tenant_client = self._tenant_client(contract)

        get_before = tenant_client.get(reverse("public_payment_step2"))
        assert get_before.status_code == 200
        assert get_before.context["invoice"] is None

        history_before = tenant_client.get(reverse("public_payment_history"))
        assert len(history_before.context["invoices"]) == 0

        post_before = tenant_client.post(
            reverse("public_payment_step2"),
            {"payment_proof_file": _proof_file()},
        )
        assert post_before.status_code == 302
        inv.refresh_from_db()
        assert inv.status == "BELUM_LUNAS"
        assert Payment.objects.filter(invoice=inv).count() == 0

        # Staff records reading on invoice_detail (rate defaults from location).
        staff_client = self._staff_client(loc, "staff_ancol_meter")
        detail_url = reverse("invoice_detail", args=[inv.pk])
        detail_get = staff_client.get(detail_url)
        assert detail_get.status_code == 200
        assert 'name="meter_reading_start"' in detail_get.content.decode("utf-8")

        detail_post = staff_client.post(
            detail_url,
            {"meter_reading_start": 200, "meter_reading_end": 260, "rate_per_kwh": "1500.00"},
        )
        assert detail_post.status_code == 302
        inv.refresh_from_db()
        assert inv.total_amount == Decimal("1590000.00")

        # Now Tenant sees invoice with electricity total and can upload proof.
        get_after = tenant_client.get(reverse("public_payment_step2"))
        assert get_after.context["invoice"] == inv
        post_after = tenant_client.post(
            reverse("public_payment_step2"),
            {"payment_proof_file": _proof_file()},
        )
        assert post_after.status_code == 200
        inv.refresh_from_db()
        assert inv.status == "MENUNGGU_VERIFIKASI"
        assert Payment.objects.filter(invoice=inv).count() == 1

    def test_token_room_and_non_electricity_location_payable_at_once_and_hide_meter_form(
        self,
    ) -> None:
        ancol, token_contract, token_inv = _make_invoice(
            location_name="Kost Ancol",
            bills_electricity=True,
            is_token=True,
            room_number="A-201",
        )
        kana, kana_contract, kana_inv = _make_invoice(
            location_name="Kost Kana",
            bills_electricity=False,
            is_token=False,
            room_number="K-101",
        )

        for loc, contract, inv, username in (
            (ancol, token_contract, token_inv, "staff_token"),
            (kana, kana_contract, kana_inv, "staff_kana"),
        ):
            staff_client = self._staff_client(loc, username)
            detail_url = reverse("invoice_detail", args=[inv.pk])
            get_detail = staff_client.get(detail_url)
            assert get_detail.status_code == 200
            assert 'name="meter_reading_start"' not in get_detail.content.decode("utf-8")

            # Direct POST to meter form is refused.
            bad_post = staff_client.post(
                detail_url,
                {"meter_reading_start": 100, "meter_reading_end": 120, "rate_per_kwh": "1500.00"},
            )
            assert bad_post.status_code == 302
            assert not ElectricityReading.objects.filter(invoice=inv).exists()

            # Tenant can see and pay immediately.
            tenant_client = self._tenant_client(contract)
            assert tenant_client.get(reverse("public_payment_step2")).context["invoice"] == inv
            pay_resp = tenant_client.post(
                reverse("public_payment_step2"),
                {"payment_proof_file": _proof_file()},
            )
            assert pay_resp.status_code == 200
            inv.refresh_from_db()
            assert inv.status == "MENUNGGU_VERIFIKASI"

    def test_w2_w3_freeze_guard_remains_active_for_metered_invoices(self) -> None:
        loc, _, inv = _make_invoice(
            location_name="Kost Ancol",
            bills_electricity=True,
            is_token=False,
            room_number="A-101",
            status="MENUNGGU_VERIFIKASI",
        )
        staff_client = self._staff_client(loc, "staff_frozen")
        resp = staff_client.post(
            reverse("invoice_detail", args=[inv.pk]),
            {"meter_reading_start": 100, "meter_reading_end": 150, "rate_per_kwh": "1500.00"},
        )
        assert resp.status_code == 302
        assert not ElectricityReading.objects.filter(invoice=inv).exists()
        with pytest.raises(ValidationError):
            ElectricityReading.objects.create(
                invoice=inv,
                meter_reading_start=100,
                meter_reading_end=150,
                rate_per_kwh=Decimal("1500.00"),
            )
