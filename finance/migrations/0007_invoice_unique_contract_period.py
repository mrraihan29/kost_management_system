from collections import defaultdict

from django.db import migrations, models


def dedupe_invoice_periods(apps, schema_editor):
    Invoice = apps.get_model('finance', 'Invoice')
    Payment = apps.get_model('finance', 'Payment')
    ElectricityReading = apps.get_model('finance', 'ElectricityReading')

    groups = defaultdict(list)
    for invoice_id, contract_id, year, month in Invoice.objects.order_by('id').values_list(
        'id', 'contract_id', 'billing_period_year', 'billing_period_month'
    ):
        groups[(contract_id, year, month)].append(invoice_id)

    conflicts = []
    duplicates_to_delete = []
    for key, ids in groups.items():
        if len(ids) < 2:
            continue
        duplicates = ids[1:]  # canonical = lowest id
        for duplicate_id in duplicates:
            status = Invoice.objects.filter(pk=duplicate_id).values_list('status', flat=True).first()
            has_payments = Payment.objects.filter(invoice_id=duplicate_id).exists()
            has_reading = ElectricityReading.objects.filter(invoice_id=duplicate_id).exists()
            if status != 'BELUM_LUNAS' or has_payments or has_reading:
                conflicts.append((key, duplicate_id, status, has_payments, has_reading))
            else:
                duplicates_to_delete.append(duplicate_id)

    if conflicts:
        raise ValueError(
            'finance/0007 dedupe aborted: duplicate invoices carry financial evidence '
            f'or non-BELUM status and require manual reconciliation: {conflicts}'
        )

    if duplicates_to_delete:
        Invoice.objects.filter(pk__in=duplicates_to_delete).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0006_invoice_billing_period_fields'),
    ]

    operations = [
        migrations.RunPython(dedupe_invoice_periods, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.UniqueConstraint(
                fields=('contract', 'billing_period_year', 'billing_period_month'),
                name='uniq_invoice_contract_period',
            ),
        ),
    ]
