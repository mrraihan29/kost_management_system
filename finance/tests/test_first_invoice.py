"""Tests for first_invoice full-month and prorated billing (EKM-22, R-023, D-020)."""

from datetime import date
from decimal import Decimal

import pytest

from core.models import KostLocation, Room
from finance.billing import first_invoice, issue, preview
from finance.models import Invoice
from tenants.models import Tenant, TenantContract
from users.models import User


def _make_contract(
    *,
    start_date: date,
    billing_mode: str,
    rent: Decimal = Decimal("1500000.00"),
    room_number: str = "R-01",
) -> TenantContract:
    loc = KostLocation.objects.create(
        name=f"Kost {billing_mode}",
        address="Jl. Test",
        billing_mode=billing_mode,
        bills_electricity=billing_mode == KostLocation.BillingMode.PER_ROOM_CYCLE.value,
    )
    room = Room.objects.create(kost_location=loc, room_number=room_number, price_monthly=rent)
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
    )


@pytest.mark.django_db
class TestFirstInvoice:
    """first_invoice issues full month for per_room_cycle and prorated for simultaneous."""

    def test_per_room_cycle_move_in_creates_full_month_from_start_date(self) -> None:
        contract = _make_contract(
            start_date=date(2026, 4, 10),
            billing_mode=KostLocation.BillingMode.PER_ROOM_CYCLE.value,
            rent=Decimal("1500000.00"),
        )
        inv = first_invoice(contract)
        assert inv.contract == contract
        assert inv.billing_period_start == date(2026, 4, 10)
        assert inv.due_date == date(2026, 4, 20)
        assert inv.base_rent_amount == Decimal("1500000.00")
        assert inv.total_amount == Decimal("1500000.00")
        assert inv.status == "BELUM_LUNAS"

    def test_simultaneous_move_in_21st_of_30_day_month_is_10_30ths(self) -> None:
        contract = _make_contract(
            start_date=date(2026, 4, 21),
            billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value,
            rent=Decimal("1500000.00"),
        )
        inv = first_invoice(contract)
        assert inv.billing_period_start == date(2026, 4, 21)
        assert inv.due_date == date(2026, 5, 1)
        assert inv.base_rent_amount == Decimal("500000.00")
        assert inv.total_amount == Decimal("500000.00")

    def test_simultaneous_move_in_on_the_1st_is_full_month_not_prorated(self) -> None:
        contract = _make_contract(
            start_date=date(2026, 4, 1),
            billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value,
            rent=Decimal("1555500.00"),
        )
        inv = first_invoice(contract)
        assert inv.billing_period_start == date(2026, 4, 1)
        assert inv.due_date == date(2026, 4, 11)
        assert inv.base_rent_amount == Decimal("1555500.00")

    @pytest.mark.parametrize(
        ("start_date", "rent", "expected"),
        [
            # 28-day month: 1/28 * 1,000,000 = 35,714.28... -> 36,000
            (date(2026, 2, 28), Decimal("1000000.00"), Decimal("36000.00")),
            # 29-day leap month: 1/29 * 1,000,000 = 34,482.75... -> 34,000
            (date(2024, 2, 29), Decimal("1000000.00"), Decimal("34000.00")),
            # 30-day month half-up tie: 15/30 * 105,000 = 52,500 -> 53,000 (not 52,000)
            (date(2026, 4, 16), Decimal("105000.00"), Decimal("53000.00")),
            # 31-day month: 1/31 * 1,000,000 = 32,258.06... -> 32,000
            (date(2026, 3, 31), Decimal("1000000.00"), Decimal("32000.00")),
        ],
    )
    def test_simultaneous_proration_rounds_to_nearest_1000_half_up_across_month_lengths(
        self, start_date: date, rent: Decimal, expected: Decimal
    ) -> None:
        contract = _make_contract(
            start_date=start_date,
            billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value,
            rent=rent,
        )
        inv = first_invoice(contract)
        assert inv.base_rent_amount == expected

    def test_next_simultaneous_run_skips_move_in_month_and_bills_full_next_month(self) -> None:
        contract = _make_contract(
            start_date=date(2026, 4, 21),
            billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value,
            rent=Decimal("1500000.00"),
        )
        loc = contract.room.kost_location
        staff = User.objects.create_user(username="staff_first", password="x", is_staff=True)

        first = first_invoice(contract)
        assert preview(loc, 2026, 4).to_create == []
        assert issue(loc, 2026, 4, by=staff) == []
        assert Invoice.objects.filter(contract=contract).count() == 1

        may_invoices = issue(loc, 2026, 5, by=staff)
        assert len(may_invoices) == 1
        may_inv = may_invoices[0]
        assert may_inv.pk != first.pk
        assert may_inv.billing_period_start == date(2026, 5, 1)
        assert may_inv.due_date == date(2026, 5, 11)
        assert may_inv.base_rent_amount == Decimal("1500000.00")

    def test_first_invoice_is_idempotent_if_called_twice(self) -> None:
        contract = _make_contract(
            start_date=date(2026, 4, 21),
            billing_mode=KostLocation.BillingMode.SIMULTANEOUS.value,
        )
        first = first_invoice(contract)
        second = first_invoice(contract)
        assert first.pk == second.pk
        assert Invoice.objects.filter(contract=contract).count() == 1
