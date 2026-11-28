"""Billing cycle calculation and invoice issuing rules (R-012, R-013, R-014, R-015, R-023, D-013, D-020)."""

import calendar
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from core.models import KostLocation, Room
from finance.models import Invoice
from tenants.models import TenantContract

LOOKAHEAD_DAYS = 7
DUE_OFFSET_DAYS = 10
SIMULTANEOUS_DUE_DAY = 11
PRORATION_ROUNDING_UNIT = Decimal("1000")

security_logger = logging.getLogger("security")


@dataclass(frozen=True, slots=True)
class Preview:
    """Simultaneous billing preview for one location and calendar month."""

    to_create: list[TenantContract]
    existing: list[Invoice]


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _create_invoice(
    contract: TenantContract,
    period_start: date,
    due_date: date,
    base_rent_amount: Decimal | None = None,
) -> Invoice | None:
    """Insert one BELUM_LUNAS invoice idempotently; IntegrityError means already issued."""
    rent = contract.monthly_rent_amount if base_rent_amount is None else base_rent_amount
    try:
        with transaction.atomic():
            return Invoice.objects.create(
                contract=contract,
                billing_period_start=period_start,
                due_date=due_date,
                base_rent_amount=rent,
                electricity_bill_amount=Decimal("0"),
                status="BELUM_LUNAS",
            )
    except IntegrityError:
        return None


def _prorate_rent(monthly_rent: Decimal, start_date: date) -> Decimal:
    """Prorate monthly rent inclusively from start_date to month end, rounded half-up to Rp 1.000."""
    if start_date.day == 1:
        return monthly_rent
    _, days_in_month = calendar.monthrange(start_date.year, start_date.month)
    prorate_days = days_in_month - start_date.day + 1
    raw = (monthly_rent * Decimal(prorate_days)) / Decimal(days_in_month)
    rounded = (raw / PRORATION_ROUNDING_UNIT).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    ) * PRORATION_ROUNDING_UNIT
    return rounded.quantize(Decimal("0.01"))


def _require_simultaneous(location: KostLocation, year: int, month: int) -> date:
    if location.billing_mode != KostLocation.BillingMode.SIMULTANEOUS.value:
        raise ValueError(f"Location '{location.name}' does not use simultaneous billing.")
    return date(year, month, 1)


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
            invoice = _create_invoice(
                contract, period_start, period_start + timedelta(days=DUE_OFFSET_DAYS)
            )
            if invoice is not None:
                created.append(invoice)
            period = _next_month(year, month)
    return created


def preview(location: KostLocation, year: int, month: int) -> Preview:
    """Return active contracts lacking an invoice and existing invoices for (year, month)."""
    _require_simultaneous(location, year, month)
    existing = list(
        Invoice.objects.filter(
            contract__room__kost_location=location,
            billing_period_year=year,
            billing_period_month=month,
        )
        .select_related("contract__tenant", "contract__room")
        .order_by("contract__room__room_number")
    )
    existing_contract_ids = {inv.contract.pk for inv in existing}
    to_create = list(
        TenantContract.objects.filter(
            is_active=True,
            room__kost_location=location,
        )
        .exclude(pk__in=existing_contract_ids)
        .select_related("tenant", "room")
        .order_by("room__room_number")
    )
    return Preview(to_create=to_create, existing=existing)


def issue(location: KostLocation, year: int, month: int, by: AbstractBaseUser) -> list[Invoice]:
    """Recompute and issue missing simultaneous invoices for (location, year, month)."""
    period_start = _require_simultaneous(location, year, month)
    due_date = date(year, month, SIMULTANEOUS_DUE_DAY)
    plan = preview(location, year, month)

    created: list[Invoice] = []
    for contract in plan.to_create:
        invoice = _create_invoice(contract, period_start, due_date)
        if invoice is not None:
            created.append(invoice)

    security_logger.info(
        "AUDIT | user=%s | action=INVOICES_ISSUED | location=%s | period=%04d-%02d | created=%d",
        by.get_username(),
        location.name,
        year,
        month,
        len(created),
    )
    return created


def first_invoice(contract: TenantContract) -> Invoice:
    """Issue a contract's first invoice: full month for per_room_cycle, prorated for simultaneous."""
    start = contract.start_date
    billing_mode = contract.room.kost_location.billing_mode
    rent = (
        _prorate_rent(contract.monthly_rent_amount, start)
        if billing_mode == KostLocation.BillingMode.SIMULTANEOUS.value
        else contract.monthly_rent_amount
    )
    invoice = _create_invoice(
        contract,
        start,
        start + timedelta(days=DUE_OFFSET_DAYS),
        base_rent_amount=rent,
    )
    if invoice is None:
        return Invoice.objects.get(
            contract=contract,
            billing_period_year=start.year,
            billing_period_month=start.month,
        )
    return invoice


def room_requires_meter(room: Room) -> bool:
    """Return True when the room's location bills electricity in-app and the room is not token."""
    return bool(room.kost_location.bills_electricity and not room.is_token_electricity)


def tenant_visible_invoices(contract: TenantContract) -> QuerySet[Invoice]:
    """Return invoices visible and payable to the Tenant, gating unread metered invoices (R-015)."""
    qs = Invoice.objects.filter(contract=contract)
    if room_requires_meter(contract.room):
        return qs.filter(electricity_reading__isnull=False)
    return qs


def invoices_needing_meter(location: KostLocation) -> QuerySet[Invoice]:
    """Return unpaid/late invoices at `location` waiting for an electricity meter reading (R-015)."""
    if not location.bills_electricity:
        return Invoice.objects.none()
    return (
        Invoice.objects.filter(
            contract__room__kost_location=location,
            contract__room__is_token_electricity=False,
            status__in=("BELUM_LUNAS", "TELAT_BAYAR"),
            electricity_reading__isnull=True,
        )
        .select_related("contract__tenant", "contract__room")
        .order_by("due_date", "contract__room__room_number")
    )
