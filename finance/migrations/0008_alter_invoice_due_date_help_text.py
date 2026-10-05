from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0007_invoice_unique_contract_period'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invoice',
            name='due_date',
            field=models.DateField(
                help_text='Jatuh tempo default: +10 hari dari tanggal tagihan',
                db_index=True,
            ),
        ),
    ]
