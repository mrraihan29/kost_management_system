from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_alter_room_capacity'),
    ]

    operations = [
        migrations.AlterField(
            model_name='room',
            name='kost_location',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='rooms',
                to='core.kostlocation',
            ),
        ),
    ]
