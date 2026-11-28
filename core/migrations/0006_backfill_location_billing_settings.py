"""Data migration backfilling billing_mode and bills_electricity per location (EKM-19)."""

from typing import Any

from django.db import migrations


def backfill_location_billing_settings(apps: Any, schema_editor: Any) -> None:
    """Assign per_room_cycle + electricity to Ancol, simultaneous without electricity elsewhere."""
    KostLocation = apps.get_model("core", "KostLocation")
    for loc in KostLocation.objects.all().order_by("pk"):
        is_ancol = "ancol" in (loc.name or "").lower()
        loc.billing_mode = "per_room_cycle" if is_ancol else "simultaneous"
        loc.bills_electricity = is_ancol
        loc.save(update_fields=["billing_mode", "bills_electricity"])
        print(
            f"EKM-19 backfill: {loc.name} -> "
            f"billing_mode={loc.billing_mode}, bills_electricity={loc.bills_electricity}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_kostlocation_billing_and_bank_settings"),
    ]

    operations = [
        migrations.RunPython(
            backfill_location_billing_settings,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
