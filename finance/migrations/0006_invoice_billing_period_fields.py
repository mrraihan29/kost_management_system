from django.db import migrations, models


def backfill_billing_period(apps, schema_editor):
    Invoice = apps.get_model('finance', 'Invoice')
    for invoice_id, start in Invoice.objects.values_list('id', 'billing_period_start'):
        Invoice.objects.filter(pk=invoice_id).update(
            billing_period_year=start.year,
            billing_period_month=start.month,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0005_payment_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='billing_period_year',
            field=models.PositiveSmallIntegerField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name='invoice',
            name='billing_period_month',
            field=models.PositiveSmallIntegerField(editable=False, null=True),
        ),
        migrations.RunPython(backfill_billing_period, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='invoice',
            name='billing_period_year',
            field=models.PositiveSmallIntegerField(editable=False),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='billing_period_month',
            field=models.PositiveSmallIntegerField(editable=False),
        ),
    ]
