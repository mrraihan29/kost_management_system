"""Tests for Tenant portal session hardening and per-contract file access (EKM-16)."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django.core.cache import cache
from django.test import Client, RequestFactory
from django.urls import reverse

from core.models import KostLocation, Room
from finance.models import Invoice, OperationCost, Payment
from finance.portal import SESSION_CONTRACT_KEY, portal_contract
from tenants.models import MaintenanceTicket, Tenant, TenantContract


@pytest.mark.django_db
class TestPortalAuthAndHelper:
    """Seam 1: portal_contract helper and step1 PIN authentication hardening."""

    @pytest.fixture(autouse=True)
    def _plain_staticfiles(self, settings: Any) -> None:
        settings.STORAGES = {
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }

    def setup_method(self) -> None:
        cache.clear()
        self.location = KostLocation.objects.create(
            name="Kost Portal", address="Jl P", electricity_rate_per_kwh=Decimal("1500")
        )
        self.room = Room.objects.create(
            kost_location=self.location, room_number="P-1", price_monthly=Decimal("1000000")
        )
        self.tenant = Tenant.objects.create(
            full_name="Tenant Portal", phone_number="0811", emergency_contact_phone="0812"
        )
        self.contract = TenantContract.objects.create(
            tenant=self.tenant,
            room=self.room,
            start_date=date(2025, 1, 1),
            monthly_rent_amount=Decimal("1000000"),
            payment_pin="654321",
            is_active=True,
        )

    def test_portal_contract_returns_active_contract_and_clears_inactive(self) -> None:
        client = Client()
        session = client.session
        session[SESSION_CONTRACT_KEY] = self.contract.pk
        session.save()

        req = RequestFactory().get("/")
        req.session = client.session
        assert portal_contract(req) == self.contract

        TenantContract.objects.filter(pk=self.contract.pk).update(is_active=False)
        assert portal_contract(req) is None
        assert SESSION_CONTRACT_KEY not in req.session

        req.session[SESSION_CONTRACT_KEY] = 999999
        assert portal_contract(req) is None
        assert SESSION_CONTRACT_KEY not in req.session

    def test_valid_pin_cycles_session_key_before_storing_contract(self) -> None:
        client = Client()
        session = client.session
        session["probe"] = 1
        session.save()
        key_before = client.session.session_key
        assert key_before is not None

        resp = client.post(
            reverse("public_payment_step1"),
            {
                "kost_location": self.location.pk,
                "room_number": "P-1",
                "pin": "654321",
            },
        )
        assert resp.status_code == 302
        assert client.session[SESSION_CONTRACT_KEY] == self.contract.pk
        assert client.session.session_key != key_before

    def test_wrong_room_and_wrong_pin_show_identical_error_message(self) -> None:
        client = Client()
        wrong_room = client.post(
            reverse("public_payment_step1"),
            {
                "kost_location": self.location.pk,
                "room_number": "NO-SUCH-ROOM",
                "pin": "654321",
            },
        )
        wrong_pin = client.post(
            reverse("public_payment_step1"),
            {
                "kost_location": self.location.pk,
                "room_number": "P-1",
                "pin": "000000",
            },
        )
        assert wrong_room.status_code == 200
        assert wrong_pin.status_code == 200
        expected = b"Lokasi, nomor kamar atau PIN salah."
        assert expected in wrong_room.content
        assert expected in wrong_pin.content

    def test_rate_limit_blocks_after_five_failures(self) -> None:
        client = Client()
        url = reverse("public_payment_step1")
        for _ in range(5):
            client.post(
                url,
                {"kost_location": self.location.pk, "room_number": "P-1", "pin": "000000"},
            )
        blocked = client.post(
            url,
            {"kost_location": self.location.pk, "room_number": "P-1", "pin": "654321"},
        )
        assert blocked.status_code == 200
        assert SESSION_CONTRACT_KEY not in client.session
        assert b"Terlalu banyak percobaan gagal." in blocked.content


@pytest.mark.django_db
class TestPortalViewsCheckoutRevocation:
    """Seam 2: checked-out contract clears session and redirects to PIN on all portal pages."""

    @pytest.fixture(autouse=True)
    def _plain_staticfiles(self, settings: Any) -> None:
        settings.STORAGES = {
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }

    def setup_method(self) -> None:
        self.location = KostLocation.objects.create(
            name="Kost Revoke", address="Jl R", electricity_rate_per_kwh=Decimal("1500")
        )
        self.room = Room.objects.create(
            kost_location=self.location, room_number="R-1", price_monthly=Decimal("1000000")
        )
        self.tenant = Tenant.objects.create(
            full_name="Tenant Revoke", phone_number="0811", emergency_contact_phone="0812"
        )
        self.contract = TenantContract.objects.create(
            tenant=self.tenant,
            room=self.room,
            start_date=date(2025, 1, 1),
            monthly_rent_amount=Decimal("1000000"),
            payment_pin="112233",
            is_active=False,
        )

    def test_checked_out_contract_clears_session_and_redirects_to_pin(self) -> None:
        pin_url = reverse("public_payment_step1")
        portal_urls = [
            reverse("public_payment_step2"),
            reverse("public_payment_history"),
            reverse("public_report_create"),
            reverse("public_report_list"),
        ]
        for url in portal_urls:
            client = Client()
            session = client.session
            session[SESSION_CONTRACT_KEY] = self.contract.pk
            session.save()

            resp = client.get(url)
            assert resp.status_code == 302, f"Expected 302 on {url}, got {resp.status_code}"
            assert resp["Location"] == pin_url
            assert SESSION_CONTRACT_KEY not in client.session


@pytest.mark.django_db
class TestTenantMediaScoping:
    """Seam 3: Tenant portal session only opens its own contract's proofs/tickets (T-008)."""

    @pytest.fixture(autouse=True)
    def _media_root(self, tmp_path: Path, settings: Any) -> None:
        settings.MEDIA_ROOT = str(tmp_path)
        self.media_root = tmp_path

    def _touch_media(self, rel_path: str) -> None:
        target = self.media_root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"img")

    def setup_method(self) -> None:
        self.location = KostLocation.objects.create(
            name="Kost Media", address="Jl M", electricity_rate_per_kwh=Decimal("1500")
        )
        self.room_a = Room.objects.create(
            kost_location=self.location, room_number="M-1", price_monthly=Decimal("1000000")
        )
        self.room_b = Room.objects.create(
            kost_location=self.location, room_number="M-2", price_monthly=Decimal("1000000")
        )
        self.tenant_a = Tenant.objects.create(
            full_name="Tenant MA",
            phone_number="0811",
            emergency_contact_phone="0812",
            ktp_photo="ktp_private/a.jpg",
        )
        self.tenant_b = Tenant.objects.create(
            full_name="Tenant MB",
            phone_number="0813",
            emergency_contact_phone="0814",
        )
        self.contract_a = TenantContract.objects.create(
            tenant=self.tenant_a,
            room=self.room_a,
            start_date=date(2025, 1, 1),
            monthly_rent_amount=Decimal("1000000"),
            is_active=True,
        )
        self.contract_b = TenantContract.objects.create(
            tenant=self.tenant_b,
            room=self.room_b,
            start_date=date(2025, 1, 1),
            monthly_rent_amount=Decimal("1000000"),
            is_active=True,
        )
        inv_a = Invoice.objects.create(
            contract=self.contract_a,
            billing_period_start=date(2025, 2, 1),
            due_date=date(2025, 2, 11),
            base_rent_amount=Decimal("1000000"),
            electricity_bill_amount=Decimal("0"),
            total_amount=Decimal("1000000"),
            status="BELUM_LUNAS",
        )
        inv_b = Invoice.objects.create(
            contract=self.contract_b,
            billing_period_start=date(2025, 2, 1),
            due_date=date(2025, 2, 11),
            base_rent_amount=Decimal("1000000"),
            electricity_bill_amount=Decimal("0"),
            total_amount=Decimal("1000000"),
            status="BELUM_LUNAS",
        )
        Payment.objects.create(invoice=inv_a, payment_proof_file="payment_proofs/a.jpg")
        Payment.objects.create(invoice=inv_b, payment_proof_file="payment_proofs/b.jpg")
        MaintenanceTicket.objects.create(
            contract=self.contract_a,
            title="TA",
            description="A",
            photo="maintenance_tickets/a.jpg",
        )
        MaintenanceTicket.objects.create(
            contract=self.contract_b,
            title="TB",
            description="B",
            photo="maintenance_tickets/b.jpg",
        )
        OperationCost.objects.create(
            kost_location=self.location,
            category="LISTRIK",
            amount=Decimal("50000"),
            description="Cost",
            incurred_date=date(2025, 2, 1),
            proof_file="operation_costs/a.jpg",
        )

    def test_contract_a_gets_404_for_contract_b_media_and_403_for_staff_folders(self) -> None:
        for rel in (
            "payment_proofs/a.jpg",
            "payment_proofs/b.jpg",
            "maintenance_tickets/a.jpg",
            "maintenance_tickets/b.jpg",
            "ktp_private/a.jpg",
            "operation_costs/a.jpg",
        ):
            self._touch_media(rel)

        client = Client()
        session = client.session
        session[SESSION_CONTRACT_KEY] = self.contract_a.pk
        session.save()

        for rel in ("payment_proofs/a.jpg", "maintenance_tickets/a.jpg"):
            resp = client.get(reverse("protected_media", kwargs={"path": rel}))
            assert resp.status_code == 200, f"Expected 200 for own {rel}"
            resp.close()

        for rel in ("payment_proofs/b.jpg", "maintenance_tickets/b.jpg"):
            resp = client.get(reverse("protected_media", kwargs={"path": rel}))
            assert resp.status_code == 404, f"Expected 404 for foreign {rel}"

        for rel in ("ktp_private/a.jpg", "operation_costs/a.jpg"):
            resp = client.get(reverse("protected_media", kwargs={"path": rel}))
            assert resp.status_code == 403, f"Expected 403 for staff-only {rel}"

        TenantContract.objects.filter(pk=self.contract_a.pk).update(is_active=False)
        revoked = client.get(reverse("protected_media", kwargs={"path": "payment_proofs/a.jpg"}))
        assert revoked.status_code == 403
        assert SESSION_CONTRACT_KEY not in client.session
