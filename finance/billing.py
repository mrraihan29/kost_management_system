"""Billing cycle calculation and invoice issuing rules (R-012, R-013, D-013)."""

import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction

from core.models import KostLocation
from finance.models import Invoice
from tenants.models import TenantContract

LOOKAHEAD_DAYS = 7
DUE_OFFSET_DAYS = 10


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def cycle_date(contract: TenantContract, year: int, month: int) -> date:
    """Return the contract's cycle date in (year, month), clamped to the month's last day."""
    _, last_day = calendar.monthrange(year, month)
    return date(year, month, min(contract.start_date.day, last_day))


def next_period(contract: TenantContract, today: date) -> tuple[int, int] | None:
    """Return the next due (year, month) within the lookahead window, or None."""
    if not contract.is_active:
        return None
    # ponytail: one indexed query per contract; prefetch latest periods if scale exceeds hundreds.
    latest = (
        Invoice.objects.filter(contract=contract)
        .order_by("-billing_period_year", "-billing_period_month")
        .values_list("billing_period_year", "billing_period_month")
        .first()
    )
    year, month = (
        _next_month(latest[0], latest[1])
        if latest is not None
        else (contract.start_date.year, contract.start_date.month)
    )
    if cycle_date(contract, year, month) <= today + timedelta(days=LOOKAHEAD_DAYS):
        return (year, month)
    return None


def issue_due(today: date) -> list[Invoice]:
    """Issue all due invoices up to today + LOOKAHEAD_DAYS for per_room_cycle locations."""
    horizon = today + timedelta(days=LOOKAHEAD_DAYS)
    contracts = TenantContract.objects.filter(
        is_active=True,
        room__kost_location__billing_mode=KostLocation.BillingMode.PER_ROOM_CYCLE,
    ).select_related("room__kost_location")

    created: list[Invoice] = []
    for contract in contracts:
        period = next_period(contract, today)
        while period is not None:
            year, month = period
            period_start = cycle_date(contract, year, month)
            if period_start > horizon:
                break
            try:
                with transaction.atomic():
                    invoice = Invoice.objects.create(
                        contract=contract,
                        billing_period_start=period_start,
                        due_date=period_start + timedelta(days=DUE_OFFSET_DAYS),
                        base_rent_amount=contract.monthly_rent_amount,
                        electricity_bill_amount=Decimal("0"),
                        status="BELUM_LUNAS",
                    )
            except IntegrityError:
                pass
            else:
                created.append(invoice)
            period = _next_month(year, month)
    return created
