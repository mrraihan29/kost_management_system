from collections import Counter

from django.core.management.base import BaseCommand

from finance.models import Invoice, Payment


class Command(BaseCommand):
    help = (
        "Read-only audit of historical Payment rows before the finance/0005 "
        "backfill. Legacy-schema safe: reads only legacy columns and never "
        "references Payment.status."
    )

    def handle(self, *args, **options):
        payments = list(
            Payment.objects.values_list("id", "invoice_id", "verified_at", "rejection_note")
        )
        invoice_status = dict(Invoice.objects.values_list("id", "status"))

        counts = Counter()
        approved_by_invoice = Counter()
        ambiguous = []
        warnings = []

        for payment_id, invoice_id, verified_at, note in payments:
            inv_status = invoice_status.get(invoice_id)
            has_note = bool(note and note.strip())
            if has_note:
                counts["REJECTED"] += 1
            elif verified_at is not None and inv_status == "LUNAS":
                counts["APPROVED"] += 1
                approved_by_invoice[invoice_id] += 1
            elif verified_at is not None:
                counts["UNCLASSIFIED"] += 1
                ambiguous.append((payment_id, "verified_at set but invoice is not LUNAS"))
            else:
                counts["PENDING"] += 1

        # W4: warning when a LUNAS invoice has no APPROVED payment evidence at all.
        # Stricter than the finance/0005 backfill warning (which only requires any
        # decision-marked payment); audit only — never repairs or invents data.
        approved_invoices = set(approved_by_invoice)
        for invoice_id, status in invoice_status.items():
            if status == "LUNAS" and invoice_id not in approved_invoices:
                warnings.append((f"invoice {invoice_id}", "LUNAS invoice without approved payment"))

        for invoice_id, total in approved_by_invoice.items():
            if total > 1:
                ambiguous.append(
                    (f"invoice {invoice_id}", f"multiple approved-classified payments ({total})")
                )

        summary = " ".join(f"{key.lower()}={value}" for key, value in sorted(counts.items()))
        self.stdout.write(f"Payment history audit: total={len(payments)} {summary}")
        if ambiguous:
            self.stdout.write(
                "AMBIGUOUS ROWS (manual reconciliation required, blocks finance/0005):"
            )
            for item, reason in ambiguous:
                self.stdout.write(f"  - {item}: {reason}")
        else:
            self.stdout.write("No ambiguous rows detected (finance/0005 may proceed).")
        if warnings:
            self.stdout.write("WARNINGS (non-blocking data-quality review):")
            for item, reason in warnings:
                self.stdout.write(f"  - {item}: {reason}")
