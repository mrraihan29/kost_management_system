from collections import defaultdict

from django.core.management.base import BaseCommand

from finance.models import ElectricityReading, Invoice, Payment


class Command(BaseCommand):
    help = (
        "Read-only audit of duplicate invoices per contract + billing period "
        "(pre-0007). Legacy-schema safe: groups by billing_period_start."
    )

    def handle(self, *args, **options):
        groups = defaultdict(list)
        rows = Invoice.objects.values_list("id", "contract_id", "billing_period_start", "status")
        for invoice_id, contract_id, start, status in rows:
            groups[(contract_id, start.year, start.month)].append((invoice_id, status))

        duplicate_groups = {key: value for key, value in groups.items() if len(value) > 1}
        if not duplicate_groups:
            self.stdout.write(
                f"Duplicate invoice audit: no duplicates found "
                f"({Invoice.objects.count()} invoices checked)."
            )
            return

        self.stdout.write("DUPLICATE INVOICE GROUPS (manual reconciliation required):")
        for (contract_id, year, month), entries in sorted(duplicate_groups.items()):
            for invoice_id, status in entries:
                has_payments = Payment.objects.filter(invoice_id=invoice_id).exists()
                has_reading = ElectricityReading.objects.filter(invoice_id=invoice_id).exists()
                self.stdout.write(
                    f"  - contract={contract_id} period={year}-{month:02d} invoice={invoice_id} "
                    f"status={status} payments={has_payments} reading={has_reading}"
                )
