"""Daily command to mark unpaid invoices past their due date as late (R-024, D-010)."""

from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from finance.services import sync_overdue_invoice_statuses


class Command(BaseCommand):
    help = "Mark unpaid BELUM_LUNAS invoices past their due date as TELAT_BAYAR."

    def handle(self, *args: Any, **options: Any) -> None:
        today = timezone.localdate()
        updated = sync_overdue_invoice_statuses(reference_date=today)
        self.stdout.write(f"mark_late_invoices date={today.isoformat()} updated={updated}")
