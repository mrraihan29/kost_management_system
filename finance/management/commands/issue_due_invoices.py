"""Daily command to issue due invoices for per-room-cycle locations (R-013, D-010)."""

from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from finance.billing import issue_due


class Command(BaseCommand):
    help = "Issue due invoices for active per-room-cycle contracts."

    def handle(self, *args: Any, **options: Any) -> None:
        today = timezone.localdate()
        created = issue_due(today)
        self.stdout.write(f"issue_due_invoices date={today.isoformat()} created={len(created)}")
