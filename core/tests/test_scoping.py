"""Tests for centralized Staff location scoping (EKM-15)."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.test import Client
from django.urls import reverse

from core.models import KostLocation, Room
from core.scoping import NoLocation, get_scoped_or_404, location_for, scoped
from finance.models import Invoice, OperationCost, Payment
from tenants.models import MaintenanceTicket, Tenant, TenantContract
from users.models import AdminProfile, User


@pytest.mark.django_db
class TestScopingFunctions:
    """Seam 1: unit tests for location_for, scoped, and get_scoped_or_404."""

    def setup_method(self) -> None:
        self.loc_a = KostLocation.objects.create(
            name="Kost A", address="Jl A", electricity_rate_per_kwh=Decimal("1500")
        )
        self.loc_b = KostLocation.objects.create(
            name="Kost B", address="Jl B", electricity_rate_per_kwh=Decimal("1500")
        )
        self.room_a = Room.objects.create(
            kost_location=self.loc_a, room_number="A-1", price_monthly=Decimal("1000000")
        )
        self.room_a2 = Room.objects.create(
            kost_location=self.loc_a, room_number="A-2", price_monthly=Decimal("1000000")
        )
        self.room_b = Room.objects.create(
            kost_location=self.loc_b, room_number="B-1", price_monthly=Decimal("1000000")
        )
        self.owner = User.objects.create_superuser(username="owner_s", email="", password="x")
        self.staff_a = User.objects.create_user(username="staff_a", password="x", is_staff=True)
        AdminProfile.objects.create(user=self.staff_a, assigned_location=self.loc_a)
        self.staff_no_profile = User.objects.create_user(
            username="staff_noprofile", password="x", is_staff=True
        )
        self.staff_null_loc = User.objects.create_user(
            username="staff_nullloc", password="x", is_staff=True
        )
        AdminProfile.objects.create(user=self.staff_null_loc, assigned_location=None)
        self.plain_user = User.objects.create_user(username="plain_u", password="x", is_staff=False)

    def test_location_for_returns_none_for_owner(self) -> None:
        assert location_for(self.owner) is None

    def test_location_for_returns_assigned_location_for_staff(self) -> None:
        assert location_for(self.staff_a) == self.loc_a

    def test_location_for_raises_no_location_for_unassigned_plain_or_anonymous(self) -> None:
        for user in (
            self.staff_no_profile,
            self.staff_null_loc,
            self.plain_user,
            AnonymousUser(),
        ):
            with pytest.raises(NoLocation):
                location_for(user)

    def test_scoped_filters_by_role_and_path(self) -> None:
        all_rooms = Room.objects.all()
        assert set(scoped(all_rooms, self.owner, "kost_location")) == {
            self.room_a,
            self.room_a2,
            self.room_b,
        }
        assert set(scoped(all_rooms, self.staff_a, "kost_location")) == {
            self.room_a,
            self.room_a2,
        }
        assert list(scoped(all_rooms, self.staff_no_profile, "kost_location")) == []
        assert list(scoped(all_rooms, self.staff_null_loc, "kost_location")) == []
        assert list(scoped(all_rooms, self.plain_user, "kost_location")) == []

    def test_get_scoped_or_404_allows_own_and_owner_blocks_foreign_with_404(self) -> None:
        assert (
            get_scoped_or_404(Room.objects.all(), self.owner, "kost_location", pk=self.room_b.pk)
            == self.room_b
        )
        assert (
            get_scoped_or_404(Room.objects.all(), self.staff_a, "kost_location", pk=self.room_a.pk)
            == self.room_a
        )
        with pytest.raises(Http404):
            get_scoped_or_404(Room.objects.all(), self.staff_a, "kost_location", pk=self.room_b.pk)
        with pytest.raises(Http404):
            get_scoped_or_404(
                Room.objects.all(), self.staff_no_profile, "kost_location", pk=self.room_a.pk
            )

    def test_get_scoped_or_404_handles_multi_hop_many_relations_without_duplicate_error(
        self,
    ) -> None:
        tenant = Tenant.objects.create(
            full_name="Repeat Tenant", phone_number="081", emergency_contact_phone="082"
        )
        TenantContract.objects.create(
            tenant=tenant,
            room=self.room_a,
            start_date=date(2025, 1, 1),
            monthly_rent_amount=Decimal("1000000"),
            is_active=False,
        )
        TenantContract.objects.create(
            tenant=tenant,
            room=self.room_a2,
            start_date=date(2025, 6, 1),
            monthly_rent_amount=Decimal("1000000"),
            is_active=True,
        )
        fetched = get_scoped_or_404(
            Tenant.objects.all(),
            self.staff_a,
            "contracts__room__kost_location",
            pk=tenant.pk,
        )
        assert fetched == tenant


@pytest.mark.django_db
class TestStaffViewScoping:
    """Seam 2: Staff of location A gets 404 on location B objects; Owner sees all."""

    @pytest.fixture(autouse=True)
    def _plain_staticfiles(self, settings: Any) -> None:
        settings.STORAGES = {
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }

    def setup_method(self) -> None:
        self.loc_a = KostLocation.objects.create(
            name="Kost A", address="Jl A", electricity_rate_per_kwh=Decimal("1500")
        )
        self.loc_b = KostLocation.objects.create(
            name="Kost B", address="Jl B", electricity_rate_per_kwh=Decimal("1500")
        )
        self.room_b = Room.objects.create(
            kost_location=self.loc_b, room_number="B-1", price_monthly=Decimal("1000000")
        )
        self.tenant_b = Tenant.objects.create(
            full_name="Tenant B", phone_number="0812", emergency_contact_phone="0813"
        )
        self.contract_b = TenantContract.objects.create(
            tenant=self.tenant_b,
            room=self.room_b,
            start_date=date(2025, 1, 1),
            monthly_rent_amount=Decimal("1000000"),
            is_active=True,
        )
        self.invoice_b = Invoice.objects.create(
            contract=self.contract_b,
            billing_period_start=date(2025, 2, 1),
            due_date=date(2025, 2, 11),
            base_rent_amount=Decimal("1000000"),
            electricity_bill_amount=Decimal("0"),
            total_amount=Decimal("1000000"),
            status="LUNAS",
        )
        self.payment_b = Payment.objects.create(
            invoice=self.invoice_b, payment_proof_file="payment_proofs/b.jpg"
        )
        self.cost_b = OperationCost.objects.create(
            kost_location=self.loc_b,
            category="LISTRIK",
            amount=Decimal("50000"),
            description="Token B",
            incurred_date=date(2025, 2, 1),
        )
        self.ticket_b = MaintenanceTicket.objects.create(
            contract=self.contract_b, title="AC B", description="Rusak"
        )

        self.owner = User.objects.create_superuser(username="owner_v", email="", password="x")
        self.staff_a = User.objects.create_user(username="staff_va", password="x", is_staff=True)
        AdminProfile.objects.create(user=self.staff_a, assigned_location=self.loc_a)
        self.staff_no_loc = User.objects.create_user(
            username="staff_vnoloc", password="x", is_staff=True
        )

        self.staff_client = Client()
        self.staff_client.force_login(self.staff_a)
        self.owner_client = Client()
        self.owner_client.force_login(self.owner)
        self.unassigned_client = Client()
        self.unassigned_client.force_login(self.staff_no_loc)

    def test_staff_a_gets_404_for_location_b_objects_across_all_views(self) -> None:
        get_urls = [
            reverse("location_update", args=[self.loc_b.pk]),
            reverse("room_edit", args=[self.room_b.pk]),
            reverse("tenant_edit", args=[self.tenant_b.pk]),
            reverse("tenant_assign_room", args=[self.tenant_b.pk]),
            reverse("invoice_detail", args=[self.invoice_b.pk]),
            reverse("print_receipt", args=[self.invoice_b.pk]),
            reverse("operation_edit", args=[self.cost_b.pk]),
            reverse("ticket_update", args=[self.ticket_b.pk]),
        ]
        for url in get_urls:
            assert self.staff_client.get(url).status_code == 404, f"Expected 404 on GET {url}"

        post_urls = [
            reverse("room_delete", args=[self.room_b.pk]),
            reverse("tenant_checkout", args=[self.tenant_b.pk]),
            reverse("tenant_delete", args=[self.tenant_b.pk]),
            reverse("verify_payment", args=[self.payment_b.pk, "approve"]),
            reverse("operation_delete", args=[self.cost_b.pk]),
        ]
        for url in post_urls:
            assert self.staff_client.post(url).status_code == 404, f"Expected 404 on POST {url}"

    def test_owner_reaches_location_b_objects_and_unassigned_staff_gets_empty_or_redirect(
        self,
    ) -> None:
        for url in (
            reverse("location_update", args=[self.loc_b.pk]),
            reverse("room_edit", args=[self.room_b.pk]),
            reverse("tenant_edit", args=[self.tenant_b.pk]),
            reverse("invoice_detail", args=[self.invoice_b.pk]),
            reverse("print_receipt", args=[self.invoice_b.pk]),
            reverse("operation_edit", args=[self.cost_b.pk]),
            reverse("ticket_update", args=[self.ticket_b.pk]),
        ):
            assert self.owner_client.get(url).status_code == 200, f"Expected 200 for owner on {url}"

        assert self.unassigned_client.get(reverse("room_add")).status_code == 302
        assert self.unassigned_client.get(reverse("operation_add")).status_code == 302
        assert self.unassigned_client.get(reverse("tenant_add")).status_code == 302
        assert self.unassigned_client.get(reverse("room_list")).status_code == 200
        assert self.unassigned_client.get(reverse("invoice_list")).status_code == 200


@pytest.mark.django_db
class TestMediaScoping:
    """Seam 3: protected media scoping blocks cross-location Staff access (T-009)."""

    @pytest.fixture(autouse=True)
    def _media_root(self, tmp_path: Path, settings: Any) -> None:
        settings.MEDIA_ROOT = str(tmp_path)
        self.media_root = tmp_path

    def _touch_media(self, rel_path: str) -> None:
        target = self.media_root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"img")

    def setup_method(self) -> None:
        self.loc_a = KostLocation.objects.create(
            name="Kost A", address="Jl A", electricity_rate_per_kwh=Decimal("1500")
        )
        self.loc_b = KostLocation.objects.create(
            name="Kost B", address="Jl B", electricity_rate_per_kwh=Decimal("1500")
        )
        self.room_a = Room.objects.create(
            kost_location=self.loc_a, room_number="A-1", price_monthly=Decimal("1000000")
        )
        self.room_b = Room.objects.create(
            kost_location=self.loc_b, room_number="B-1", price_monthly=Decimal("1000000")
        )
        self.tenant_a = Tenant.objects.create(
            full_name="Tenant A",
            phone_number="0811",
            emergency_contact_phone="0812",
            ktp_photo="ktp_private/a.jpg",
        )
        self.tenant_b = Tenant.objects.create(
            full_name="Tenant B",
            phone_number="0813",
            emergency_contact_phone="0814",
            ktp_photo="ktp_private/b.jpg",
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
        OperationCost.objects.create(
            kost_location=self.loc_a,
            category="LISTRIK",
            amount=Decimal("50000"),
            description="A",
            incurred_date=date(2025, 2, 1),
            proof_file="operation_costs/a.jpg",
        )
        OperationCost.objects.create(
            kost_location=self.loc_b,
            category="LISTRIK",
            amount=Decimal("50000"),
            description="B",
            incurred_date=date(2025, 2, 1),
            proof_file="operation_costs/b.jpg",
        )
        MaintenanceTicket.objects.create(
            contract=self.contract_a,
            title="A",
            description="A",
            photo="maintenance_tickets/a.jpg",
        )
        MaintenanceTicket.objects.create(
            contract=self.contract_b,
            title="B",
            description="B",
            photo="maintenance_tickets/b.jpg",
        )

        self.owner = User.objects.create_superuser(username="owner_m", email="", password="x")
        self.staff_a = User.objects.create_user(username="staff_ma", password="x", is_staff=True)
        AdminProfile.objects.create(user=self.staff_a, assigned_location=self.loc_a)
        self.staff_no_loc = User.objects.create_user(
            username="staff_mnoloc", password="x", is_staff=True
        )

        self.staff_client = Client()
        self.staff_client.force_login(self.staff_a)
        self.owner_client = Client()
        self.owner_client.force_login(self.owner)
        self.unassigned_client = Client()
        self.unassigned_client.force_login(self.staff_no_loc)

    def _create_all_files(self) -> tuple[list[str], list[str]]:
        loc_a_files = [
            "ktp_private/a.jpg",
            "payment_proofs/a.jpg",
            "operation_costs/a.jpg",
            "maintenance_tickets/a.jpg",
        ]
        loc_b_files = [
            "ktp_private/b.jpg",
            "payment_proofs/b.jpg",
            "operation_costs/b.jpg",
            "maintenance_tickets/b.jpg",
        ]
        for rel in loc_a_files + loc_b_files:
            self._touch_media(rel)
        return loc_a_files, loc_b_files

    def test_staff_a_gets_404_for_location_b_media_and_200_for_own(self) -> None:
        loc_a_files, loc_b_files = self._create_all_files()
        for rel in loc_b_files:
            resp = self.staff_client.get(reverse("protected_media", kwargs={"path": rel}))
            assert resp.status_code == 404, f"Expected 404 for {rel}"
        for rel in loc_a_files:
            resp = self.staff_client.get(reverse("protected_media", kwargs={"path": rel}))
            assert resp.status_code == 200, f"Expected 200 for {rel}"
            resp.close()

    def test_owner_sees_all_unassigned_gets_404_and_tenant_session_allowed(self) -> None:
        loc_a_files, loc_b_files = self._create_all_files()
        for rel in loc_a_files + loc_b_files:
            resp = self.owner_client.get(reverse("protected_media", kwargs={"path": rel}))
            assert resp.status_code == 200
            resp.close()

        assert (
            self.unassigned_client.get(
                reverse("protected_media", kwargs={"path": "ktp_private/a.jpg"})
            ).status_code
            == 404
        )

        tenant_client = Client()
        session = tenant_client.session
        session["verified_contract_id"] = self.contract_a.pk
        session.save()
        resp = tenant_client.get(
            reverse("protected_media", kwargs={"path": "payment_proofs/a.jpg"})
        )
        assert resp.status_code == 200
        resp.close()


def test_no_direct_assigned_location_reads_outside_allowlist() -> None:
    """Guardrail (EKM-15): only core/scoping.py and tenants/forms.py read assigned_location."""
    repo_root = Path(__file__).resolve().parents[2]
    allowlist = {"core/scoping.py", "tenants/forms.py"}
    offenders: list[str] = []
    for app in ("core", "finance", "tenants"):
        for py_file in (repo_root / app).rglob("*.py"):
            rel = py_file.relative_to(repo_root).as_posix()
            if "/migrations/" in rel or "/tests/" in rel or rel in allowlist:
                continue
            if "assigned_location" in py_file.read_text(encoding="utf-8"):
                offenders.append(rel)
    assert offenders == [], f"Direct assigned_location reads found: {offenders}"
