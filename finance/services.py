"""Invoice status maintenance service (R-024, D-010)."""

from datetime import date

from django.utils import timezone

from .models import Invoice


def sync_overdue_invoice_statuses(reference_date: date | None = None) -> int:
    """Mark unpaid BELUM_LUNAS invoices past due_date as TELAT_BAYAR without adding fees."""
    today = timezone.localdate() if reference_date is None else reference_date
    return Invoice.objects.filter(
        status="BELUM_LUNAS",
        due_date__lt=today,
    ).update(status="TELAT_BAYAR")
