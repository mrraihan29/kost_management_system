from collections import Counter

from django.db import migrations, models


def backfill_payment_status(apps, schema_editor):
    Payment = apps.get_model('finance', 'Payment')
    Invoice = apps.get_model('finance', 'Invoice')

    ambiguous = []
    warnings = []
    approved_by_invoice = Counter()
    marked_invoices = set()

    rows = Payment.objects.values_list('id', 'invoice_id', 'verified_at', 'rejection_note')
    invoice_status = dict(Invoice.objects.values_list('id', 'status'))

    for payment_id, invoice_id, verified_at, note in rows:
        inv_status = invoice_status.get(invoice_id)
        has_note = bool(note and note.strip())
        if has_note:
            new_status = 'REJECTED'
            marked_invoices.add(invoice_id)
        elif verified_at is not None and inv_status == 'LUNAS':
            new_status = 'APPROVED'
            approved_by_invoice[invoice_id] += 1
            marked_invoices.add(invoice_id)
        elif verified_at is not None:
            ambiguous.append((payment_id, 'verified_at set but invoice is not LUNAS'))
            marked_invoices.add(invoice_id)
            new_status = None
        else:
            new_status = 'PENDING'
        if new_status is not None:
            Payment.objects.filter(pk=payment_id).update(status=new_status)

    # Invoice-level anomaly: no Payment row to classify, so this cannot make the
    # backfill unsafe — reported as a warning for manual data-quality review.
    for invoice_id, status in invoice_status.items():
        if status == 'LUNAS' and invoice_id not in marked_invoices:
            warnings.append(
                (f'invoice {invoice_id}', 'LUNAS invoice without decision-marked payment')
            )

    for invoice_id, total in approved_by_invoice.items():
        if total > 1:
            ambiguous.append(
                (f'invoice {invoice_id}', f'multiple approved-classified payments ({total})')
            )

    if warnings:
        print(
            'finance/0005 warning: invoice-level anomalies detected (backfill proceeds; '
            f'manual data-quality review recommended): {warnings}'
        )

    if ambiguous:
        raise ValueError(
            'finance/0005 backfill aborted: ambiguous historical payment data '
            f'requires manual reconciliation: {ambiguous}'
        )


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0004_alter_invoice_billing_period_start_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Menunggu Keputusan'),
                    ('APPROVED', 'Disetujui'),
                    ('REJECTED', 'Ditolak'),
                ],
                db_index=True,
                default='PENDING',
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_payment_status, migrations.RunPython.noop),
    ]
