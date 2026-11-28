"""Tests for per-room-cycle billing dates, issuing, and daily command (EKM-20)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import IntegrityError
from django.utils import timezone

from core.models import KostLocation, Room
from finance.billing import cycle_date, issue_due, next_period
from finance.models import Invoice, Payment
from tenants.models import Tenant, TenantContract


def _make_contract(
    *,
    start_date: date,
    billing_mode: str = KostLocation.BillingMode.PER_ROOM_CYCLE.value,
    location_name: str = "Kost Ancol",
    room_number: str = "A-101",
    is_active: bool = True,
) -> TenantContract:
    loc = KostLocation.objects.create(
        name=location_name,
        address="Jl. Test",
        billing_mode=billing_mode,
        bills_electricity=billing_mode == KostLocation.BillingMode.PER_ROOM_CYCLE.value,
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
    return TenantContract.objects.create(
        tenant=tenant,
        room=room,
        start_date=start_date,
        monthly_rent_amount=Decimal("1500000.00"),
        is_active=is_active,
    )


@pytest.mark.django_db
class TestCycleDate:
    """cycle_date anchors to contract.start_date.day and clamps to month length."""

    def test_constant_day_10_across_months(self) -> None:
        contract = _make_contract(start_date=date(2026, 1, 10))
        assert cycle_date(contract, 2026, 1) == date(2026, 1, 10)
        assert cycle_date(contract, 2026, 2) == date(2026, 2, 10)
        assert cycle_date(contract, 2026, 3) == date(2026, 3, 10)
        assert cycle_date(contract, 2027, 1) == date(2027, 1, 10)

    def test_start_day_31_clamps_in_shorter_and_leap_months_and_restores(self) -> None:
        contract = _make_contract(start_date=date(2024, 1, 31))
        assert cycle_date(contract, 2024, 2) == date(2024, 2, 29)
        assert cycle_date(contract, 2026, 2) == date(2026, 2, 28)
        assert cycle_date(contract, 2026, 3) == date(2026, 3, 31)
        assert cycle_date(contract, 2026, 4) == date(2026, 4, 30)

    def test_leap_day_start_clamps_to_28_in_non_leap_feb_and_29_otherwise(self) -> None:
        contract = _make_contract(start_date=date(2024, 2, 29))
        assert cycle_date(contract, 2025, 2) == date(2025, 2, 28)
        assert cycle_date(contract, 2025, 3) == date(2025, 3, 29)
        assert cycle_date(contract, 2028, 2) == date(2028, 2, 29)


@pytest.mark.django_db
class TestNextPeriod:
    """next_period returns the next unissued period within the 7-day lookahead."""

    def test_lookahead_boundary_h8_vs_h7(self) -> None:
        contract = _make_contract(start_date=date(2026, 3, 10))
        assert next_period(contract, date(2026, 3, 2)) is None
        assert next_period(contract, date(2026, 3, 3)) == (2026, 3)

    def test_inactive_contract_returns_none(self) -> None:
        contract = _make_contract(start_date=date(2026, 3, 10), is_active=False)
        assert next_period(contract, date(2026, 3, 10)) is None

    def test_year_boundary_advances_december_to_january(self) -> None:
        contract = _make_contract(start_date=date(2026, 12, 2))
        Invoice.objects.create(
            contract=contract,
            billing_period_start=date(2026, 12, 2),
            due_date=date(2026, 12, 12),
            base_rent_amount=contract.monthly_rent_amount,
            status="BELUM_LUNAS",
        )
        assert next_period(contract, date(2026, 12, 25)) is None
        assert next_period(contract, date(2026, 12, 26)) == (2027, 1)

    def test_late_payment_does_not_shift_next_cycle_date(self) -> None:
        contract = _make_contract(start_date=date(2026, 1, 10))
        jan_invoice = Invoice.objects.create(
            contract=contract,
            billing_period_start=date(2026, 1, 10),
            due_date=date(2026, 1, 20),
            base_rent_amount=contract.monthly_rent_amount,
            status="LUNAS",
        )
        Payment.objects.create(
            invoice=jan_invoice,
            payment_proof_file="payment_proofs/late.jpg",
            status="APPROVED",
            verified_at=datetime(2026, 1, 28, 12, 0, tzinfo=UTC),
        )
        period = next_period(contract, date(2026, 2, 3))
        assert period == (2026, 2)
        assert cycle_date(contract, 2026, 2) == date(2026, 2, 10)


@pytest.mark.django_db
class TestIssueDue:
    """issue_due creates due per_room_cycle invoices idempotently with catch-up."""

    def test_issues_single_invoice_with_due_plus_10_and_rent_amount(self) -> None:
        contract = _make_contract(start_date=date(2026, 1, 10))
        created = issue_due(date(2026, 1, 3))
        assert len(created) == 1
        inv = created[0]
        assert inv.contract == contract
        assert inv.billing_period_start == date(2026, 1, 10)
        assert inv.due_date == date(2026, 1, 20)
        assert inv.base_rent_amount == contract.monthly_rent_amount
        assert inv.electricity_bill_amount == Decimal("0")
        assert inv.total_amount == contract.monthly_rent_amount
        assert inv.status == "BELUM_LUNAS"

    def test_idempotent_when_run_twice_same_day(self) -> None:
        contract = _make_contract(start_date=date(2026, 1, 10))
        first = issue_due(date(2026, 1, 3))
        second = issue_due(date(2026, 1, 3))
        assert [i.contract for i in first] == [contract]
        assert second == []
        assert Invoice.objects.filter(contract=contract).count() == 1

    def test_catches_up_missed_days_and_multiple_periods(self) -> None:
        _make_contract(start_date=date(2026, 1, 10))
        created = issue_due(date(2026, 3, 4))
        assert [(i.billing_period_start, i.due_date) for i in created] == [
            (date(2026, 1, 10), date(2026, 1, 20)),
            (date(2026, 2, 10), date(2026, 2, 20)),
            (date(2026, 3, 10), date(2026, 3, 20)),
        ]
        assert issue_due(date(2026, 3, 4)) == []

    def test_integrity_error_is_treated_as_already_issued(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        contract = _make_contract(start_date=date(2026, 1, 10))
        real_create = Invoice.objects.create

        def flaky_create(**kwargs: object) -> Invoice:
            if kwargs.get("billing_period_start") == date(2026, 1, 10):
                raise IntegrityError("duplicate period")
            return real_create(**kwargs)

        monkeypatch.setattr(Invoice.objects, "create", flaky_create)
        created = issue_due(date(2026, 2, 3))
        assert [i.billing_period_start for i in created] == [date(2026, 2, 10)]
        assert Invoice.objects.filter(contract=contract).count() == 1

    def test_skips_simultaneous_and_inactive_and_ignores_location_name(self) -> None:
        _make_contract(
            start_date=date(2026, 1, 10),
            billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value,
            location_name="Ancol Renamed Sim",
            room_number="S-101",
        )
        _make_contract(
            start_date=date(2026, 1, 10),
            billing_mode=KostLocation.BillingMode.PER_ROOM_CYCLE.value,
            location_name="Kost Melati",
            room_number="M-101",
            is_active=False,
        )
        active_non_ancol = _make_contract(
            start_date=date(2026, 1, 10),
            billing_mode=KostLocation.BillingMode.PER_ROOM_CYCLE.value,
            location_name="Kost Kenanga",
            room_number="K-101",
        )
        created = issue_due(date(2026, 1, 3))
        assert [i.contract for i in created] == [active_non_ancol]


@pytest.mark.django_db
class TestIssueDueInvoicesCommand:
    """manage.py issue_due_invoices uses Asia/Jakarta localdate and prints one summary line."""

    def test_uses_jakarta_localdate_across_utc_boundary_and_prints_one_line(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        contract = _make_contract(start_date=date(2026, 2, 10))
        # 2026-02-02 17:05 UTC == 2026-02-03 00:05 Asia/Jakarta (7 days before 2026-02-10)
        monkeypatch.setattr(
            timezone,
            "now",
            lambda: datetime(2026, 2, 2, 17, 5, tzinfo=UTC),
        )
        out = StringIO()
        call_command("issue_due_invoices", stdout=out)
        lines = out.getvalue().strip().splitlines()
        assert lines == ["issue_due_invoices date=2026-02-03 created=1"]
        assert Invoice.objects.filter(
            contract=contract, billing_period_start=date(2026, 2, 10)
        ).exists()

    def test_command_repeat_reports_zero_created(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_contract(start_date=date(2026, 2, 10))
        monkeypatch.setattr(
            timezone,
            "now",
            lambda: datetime(2026, 2, 2, 17, 5, tzinfo=UTC),
        )
        call_command("issue_due_invoices", stdout=StringIO())
        out = StringIO()
        call_command("issue_due_invoices", stdout=out)
        assert out.getvalue().strip().splitlines() == [
            "issue_due_invoices date=2026-02-03 created=0"
        ]
