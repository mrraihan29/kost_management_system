"""Tests for simultaneous invoice preview, issuing, and Staff view (EKM-21)."""

import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core.models import KostLocation, Room
from finance.billing import Preview, issue, preview
from finance.models import Invoice
from tenants.models import Tenant, TenantContract
from users.models import AdminProfile, User


def _make_location(*, name: str, billing_mode: str) -> KostLocation:
    return KostLocation.objects.create(
        name=name,
        address="Jl. Test",
        billing_mode=billing_mode,
        bills_electricity=billing_mode == KostLocation.BillingMode.PER_ROOM_CYCLE.value,
    )


def _add_contract(
    location: KostLocation,
    *,
    room_number: str,
    rent: Decimal = Decimal("1200000.00"),
    start_date: date = date(2026, 1, 10),
    is_active: bool = True,
) -> TenantContract:
    room = Room.objects.create(
        kost_location=location,
        room_number=room_number,
        price_monthly=rent,
    )
    tenant = Tenant.objects.create(
        full_name=f"Penghuni {room_number}",
        phone_number="08123456789",
        emergency_contact_phone="08129876543",
    )
    return TenantContract.objects.create(
        tenant=tenant,
        room=room,
        start_date=start_date,
        monthly_rent_amount=rent,
        is_active=is_active,
    )


@pytest.mark.django_db
class TestSimultaneousPreviewAndIssue:
    """preview and issue handle simultaneous billing idempotently with audit logging."""

    def test_preview_splits_to_create_and_existing_ordered_by_room(self) -> None:
        loc = _make_location(
            name="Kost Kana", billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value
        )
        other_loc = _make_location(
            name="Kost UNS", billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value
        )
        c_b = _add_contract(loc, room_number="B-02")
        c_a = _add_contract(loc, room_number="A-01")
        _add_contract(loc, room_number="C-03", is_active=False)
        _add_contract(other_loc, room_number="U-01")

        existing_inv = Invoice.objects.create(
            contract=c_a,
            billing_period_start=date(2026, 4, 1),
            due_date=date(2026, 4, 11),
            base_rent_amount=c_a.monthly_rent_amount,
            status="BELUM_LUNAS",
        )

        result = preview(loc, 2026, 4)
        assert isinstance(result, Preview)
        assert result.to_create == [c_b]
        assert result.existing == [existing_inv]

    def test_preview_and_issue_reject_per_room_cycle_location(self) -> None:
        ancol = _make_location(
            name="Kost Ancol", billing_mode=KostLocation.BillingMode.PER_ROOM_CYCLE.value
        )
        staff = User.objects.create_user(username="staff_ancol", password="x", is_staff=True)
        with pytest.raises(ValueError):
            preview(ancol, 2026, 4)
        with pytest.raises(ValueError):
            issue(ancol, 2026, 4, by=staff)

    def test_issue_creates_dated_1st_due_11th_logs_audit_and_is_idempotent(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        loc = _make_location(
            name="Kost Kana", billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value
        )
        c1 = _add_contract(loc, room_number="K-01", rent=Decimal("1300000.00"))
        c2 = _add_contract(loc, room_number="K-02", rent=Decimal("1400000.00"))
        staff = User.objects.create_user(username="staff_kana", password="x", is_staff=True)

        with caplog.at_level(logging.INFO, logger="security"):
            created = issue(loc, 2026, 5, by=staff)

        assert len(created) == 2
        for inv in created:
            assert inv.billing_period_start == date(2026, 5, 1)
            assert inv.due_date == date(2026, 5, 11)
            assert inv.base_rent_amount == inv.contract.monthly_rent_amount
            assert inv.total_amount == inv.contract.monthly_rent_amount
            assert inv.status == "BELUM_LUNAS"
        assert {i.contract for i in created} == {c1, c2}

        audit_msgs = [r.getMessage() for r in caplog.records if "INVOICES_ISSUED" in r.getMessage()]
        assert len(audit_msgs) == 1
        assert "staff_kana" in audit_msgs[0]
        assert "Kost Kana" in audit_msgs[0]
        assert "2026-05" in audit_msgs[0]
        assert "created=2" in audit_msgs[0]

        # Repeat returns 0 created and preview shows 0 to create.
        second = issue(loc, 2026, 5, by=staff)
        assert second == []
        after = preview(loc, 2026, 5)
        assert after.to_create == []
        assert len(after.existing) == 2

    def test_issue_treats_integrity_error_as_already_issued(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        loc = _make_location(
            name="Kost Kana", billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value
        )
        c1 = _add_contract(loc, room_number="K-01")
        c2 = _add_contract(loc, room_number="K-02")
        staff = User.objects.create_user(username="staff_race", password="x", is_staff=True)

        real_create = Invoice.objects.create

        def flaky_create(**kwargs: object) -> Invoice:
            if kwargs.get("contract") == c1:
                raise IntegrityError("concurrent issue")
            return real_create(**kwargs)

        monkeypatch.setattr(Invoice.objects, "create", flaky_create)
        created = issue(loc, 2026, 6, by=staff)
        assert [i.contract for i in created] == [c2]


@pytest.mark.django_db
class TestSimultaneousIssueView:
    """View tests for Staff preview/confirm, mode gating (404), and Owner access."""

    @pytest.fixture(autouse=True)
    def _plain_staticfiles(self, settings: Any) -> None:
        settings.STORAGES = {
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }

    def setup_method(self) -> None:
        self.sim_loc = _make_location(
            name="Kost Kana", billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value
        )
        self.other_sim_loc = _make_location(
            name="Kost UNS", billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value
        )
        self.cycle_loc = _make_location(
            name="Kost Ancol", billing_mode=KostLocation.BillingMode.PER_ROOM_CYCLE.value
        )

        self.owner = User.objects.create_superuser(username="owner_sim", email="", password="x")
        self.sim_staff = User.objects.create_user(username="staff_sim", password="x", is_staff=True)
        AdminProfile.objects.create(user=self.sim_staff, assigned_location=self.sim_loc)

        self.cycle_staff = User.objects.create_user(
            username="staff_cycle", password="x", is_staff=True
        )
        AdminProfile.objects.create(user=self.cycle_staff, assigned_location=self.cycle_loc)

        self.sim_client = Client()
        self.sim_client.force_login(self.sim_staff)
        self.cycle_client = Client()
        self.cycle_client.force_login(self.cycle_staff)
        self.owner_client = Client()
        self.owner_client.force_login(self.owner)

    def test_invoice_list_shows_issue_action_only_for_simultaneous(self) -> None:
        sim_body = self.sim_client.get(reverse("invoice_list")).content.decode("utf-8")
        assert "Terbitkan tagihan" in sim_body
        assert reverse("issue_invoices") in sim_body

        cycle_body = self.cycle_client.get(reverse("invoice_list")).content.decode("utf-8")
        assert "Terbitkan tagihan" not in cycle_body
        assert reverse("issue_invoices") not in cycle_body

    def test_preview_shows_count_existing_rooms_month_options_and_confirm_issues(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            timezone,
            "now",
            lambda: datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
        )
        c1 = _add_contract(self.sim_loc, room_number="K-01", rent=Decimal("1500000.00"))
        c2 = _add_contract(self.sim_loc, room_number="K-02", rent=Decimal("1600000.00"))
        Invoice.objects.create(
            contract=c1,
            billing_period_start=date(2026, 4, 1),
            due_date=date(2026, 4, 11),
            base_rent_amount=c1.monthly_rent_amount,
            status="BELUM_LUNAS",
        )

        url = reverse("issue_invoices")
        get_resp = self.sim_client.get(url)
        assert get_resp.status_code == 200
        body = get_resp.content.decode("utf-8")
        assert "1 tagihan akan dibuat" in body
        assert "K-01" in body
        assert "K-02" in body
        assert "April 2026" in body
        assert "Mei 2026" in body
        for forbidden in ("cdn.jsdelivr.net", "cdnjs.cloudflare.com", "fonts.googleapis.com"):
            assert forbidden not in body

        # Choosing next month previews all 2 contracts.
        next_body = self.sim_client.get(f"{url}?period=2026-05").content.decode("utf-8")
        assert "2 tagihan akan dibuat" in next_body

        # Confirm POST for this month (2026-04) creates only c2, dated 1st, due 11th.
        post_resp = self.sim_client.post(url, {"period": "2026-04"}, follow=True)
        assert post_resp.status_code == 200
        assert "1 tagihan diterbitkan" in post_resp.content.decode("utf-8")
        inv = Invoice.objects.get(contract=c2, billing_period_year=2026, billing_period_month=4)
        assert inv.billing_period_start == date(2026, 4, 1)
        assert inv.due_date == date(2026, 4, 11)

        # Repeat shows 0 before confirming and creates 0 on POST.
        repeat_get = self.sim_client.get(url).content.decode("utf-8")
        assert "0 tagihan akan dibuat" in repeat_get
        repeat_post = self.sim_client.post(url, {"period": "2026-04"}, follow=True)
        assert "0 tagihan diterbitkan" in repeat_post.content.decode("utf-8")
        assert Invoice.objects.filter(contract__room__kost_location=self.sim_loc).count() == 2

    def test_per_room_cycle_staff_gets_404_on_get_and_post(self) -> None:
        url = reverse("issue_invoices")
        assert self.cycle_client.get(url).status_code == 404
        assert self.cycle_client.post(url, {"period": "2026-04"}).status_code == 404

    def test_staff_cannot_issue_for_another_location_or_invalid_period(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            timezone,
            "now",
            lambda: datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
        )
        other_contract = _add_contract(self.other_sim_loc, room_number="U-01")
        url = reverse("issue_invoices")
        resp = self.sim_client.post(
            url, {"period": "2026-04", "location": str(self.other_sim_loc.pk)}
        )
        assert resp.status_code == 302
        assert not Invoice.objects.filter(contract=other_contract).exists()

        bad = self.sim_client.post(url, {"period": "2026-01"})
        assert bad.status_code == 400

    def test_owner_can_select_simultaneous_location_and_gets_404_for_cycle_location(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            timezone,
            "now",
            lambda: datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
        )
        c_uns = _add_contract(self.other_sim_loc, room_number="U-01")
        url = reverse("issue_invoices")

        assert self.owner_client.get(f"{url}?location={self.cycle_loc.pk}").status_code == 404
        assert (
            self.owner_client.post(
                url, {"period": "2026-04", "location": str(self.cycle_loc.pk)}
            ).status_code
            == 404
        )

        get_uns = self.owner_client.get(f"{url}?location={self.other_sim_loc.pk}&period=2026-04")
        assert get_uns.status_code == 200
        assert "1 tagihan akan dibuat" in get_uns.content.decode("utf-8")

        post_uns = self.owner_client.post(
            url, {"period": "2026-04", "location": str(self.other_sim_loc.pk)}, follow=True
        )
        assert "1 tagihan diterbitkan" in post_uns.content.decode("utf-8")
        assert Invoice.objects.filter(contract=c_uns, billing_period_month=4).exists()
