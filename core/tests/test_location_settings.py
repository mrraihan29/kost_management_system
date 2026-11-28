"""Tests for KostLocation billing mode, electricity billing, and bank settings (EKM-19)."""

import logging
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client
from django.urls import reverse

from core.models import OWNER_ONLY_LOCATION_FIELDS, KostLocation, validate_bank_account_number
from users.models import AdminProfile, User


@pytest.mark.django_db(transaction=True)
def test_migrations_forward_and_backward_backfill_ancol_and_other(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Migrations 0005/0006 populate billing defaults cleanly and roll back to 0004."""
    migrate_from = [("core", "0004_alter_room_kost_location")]
    migrate_to = [("core", "0006_backfill_location_billing_settings")]

    executor: Any = MigrationExecutor(connection)
    executor.migrate(migrate_from)
    try:
        old_apps = executor.loader.project_state(migrate_from).apps
        OldLocation = old_apps.get_model("core", "KostLocation")
        OldLocation.objects.create(
            name="Kost Ancol Timur",
            address="Jl. Ancol",
            electricity_rate_per_kwh=Decimal("1500.00"),
        )
        OldLocation.objects.create(
            name="Kost Kana",
            address="Jl. Kana",
            electricity_rate_per_kwh=Decimal("1500.00"),
        )

        executor = MigrationExecutor(connection)
        executor.migrate(migrate_to)
        captured = capsys.readouterr().out
        assert "Kost Ancol Timur -> billing_mode=per_room_cycle, bills_electricity=True" in captured
        assert "Kost Kana -> billing_mode=simultaneous, bills_electricity=False" in captured

        new_apps = executor.loader.project_state(migrate_to).apps
        NewLocation = new_apps.get_model("core", "KostLocation")
        ancol = NewLocation.objects.get(name="Kost Ancol Timur")
        kana = NewLocation.objects.get(name="Kost Kana")
        assert ancol.billing_mode == "per_room_cycle"
        assert ancol.bills_electricity is True
        assert ancol.bank_name == ""
        assert ancol.bank_account_number == ""
        assert ancol.bank_account_holder == ""
        assert kana.billing_mode == "simultaneous"
        assert kana.bills_electricity is False

        executor = MigrationExecutor(connection)
        executor.migrate([("core", "0005_kostlocation_billing_and_bank_settings")])
        executor = MigrationExecutor(connection)
        executor.migrate(migrate_from)
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(migrate_to)


class TestBankAccountNumberValidation:
    """Bank account number allows blank or 6-20 digits with spaces."""

    @pytest.mark.parametrize(
        "value",
        ["", "   ", "123456", "1234 5678 9012", "12345678901234567890"],
    )
    def test_valid_account_numbers_pass(self, value: str) -> None:
        validate_bank_account_number(value)

    @pytest.mark.parametrize(
        "value",
        ["12345", "123456789012345678901", "123-456-789", "BCA123456", "12345a"],
    )
    def test_invalid_account_numbers_raise(self, value: str) -> None:
        with pytest.raises(ValidationError):
            validate_bank_account_number(value)


@pytest.mark.django_db
class TestLocationSettingsAuthorizationAndAudit:
    """Owner edits the five settings with T-013 audit logging; Staff gets 403 everywhere."""

    @pytest.fixture(autouse=True)
    def _plain_staticfiles(self, settings: Any) -> None:
        settings.STORAGES = {
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }

    def setup_method(self) -> None:
        self.loc = KostLocation.objects.create(
            name="Kost Kana",
            address="Jl. Kana No. 1",
            electricity_rate_per_kwh=Decimal("1500.00"),
            billing_mode=KostLocation.BillingMode.SIMULTANEOUS,
            bills_electricity=False,
        )
        self.owner = User.objects.create_superuser(username="owner_loc", email="", password="x")
        self.staff = User.objects.create_user(username="staff_loc", password="x", is_staff=True)
        AdminProfile.objects.create(user=self.staff, assigned_location=self.loc)

        self.owner_client = Client()
        self.owner_client.force_login(self.owner)
        self.staff_client = Client()
        self.staff_client.force_login(self.staff)

    def test_owner_form_renders_plat_nomor_and_saves_with_per_field_audit(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        url = reverse("location_update", args=[self.loc.pk])
        get_resp = self.owner_client.get(url)
        assert get_resp.status_code == 200
        body = get_resp.content.decode("utf-8")
        assert "cdn.jsdelivr.net" not in body
        assert "cdnjs.cloudflare.com" not in body
        assert 'value="1500.00"' in body
        assert 'value="1500,00"' not in body
        for field in OWNER_ONLY_LOCATION_FIELDS:
            assert f'name="{field}"' in body

        with caplog.at_level(logging.INFO, logger="security"):
            post_resp = self.owner_client.post(
                url,
                {
                    "name": "Kost Kana",
                    "address": "Jl. Kana No. 1",
                    "electricity_rate_per_kwh": "1500.00",
                    "description": "",
                    "billing_mode": KostLocation.BillingMode.PER_ROOM_CYCLE,
                    "bills_electricity": "on",
                    "bank_name": "BCA",
                    "bank_account_number": "1234 5678 90",
                    "bank_account_holder": "Evy Kost",
                },
            )
        assert post_resp.status_code == 302
        self.loc.refresh_from_db()
        assert self.loc.billing_mode == KostLocation.BillingMode.PER_ROOM_CYCLE
        assert self.loc.bills_electricity is True
        assert self.loc.bank_name == "BCA"
        assert self.loc.bank_account_number == "1234 5678 90"
        assert self.loc.bank_account_holder == "Evy Kost"

        audit_msgs = [
            r.getMessage() for r in caplog.records if "LOCATION_SETTING_CHANGED" in r.getMessage()
        ]
        assert len(audit_msgs) == 5
        joined = "\n".join(audit_msgs)
        assert "owner_loc" in joined
        assert "Kost Kana" in joined
        assert "field=billing_mode" in joined
        assert "simultaneous" in joined
        assert "per_room_cycle" in joined
        assert "field=bank_account_number" in joined

        # Submitting unchanged values creates no additional audit lines.
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="security"):
            self.owner_client.post(
                url,
                {
                    "name": "Kost Kana",
                    "address": "Jl. Kana No. 2",
                    "electricity_rate_per_kwh": "1500.00",
                    "description": "",
                    "billing_mode": KostLocation.BillingMode.PER_ROOM_CYCLE,
                    "bills_electricity": "on",
                    "bank_name": "BCA",
                    "bank_account_number": "1234 5678 90",
                    "bank_account_holder": "Evy Kost",
                },
            )
        assert not [r for r in caplog.records if "LOCATION_SETTING_CHANGED" in r.getMessage()]

    def test_staff_cannot_see_or_post_owner_only_fields_in_view_or_admin(self) -> None:
        url = reverse("location_update", args=[self.loc.pk])
        get_resp = self.staff_client.get(url)
        assert get_resp.status_code == 200
        body = get_resp.content.decode("utf-8")
        for field in OWNER_ONLY_LOCATION_FIELDS:
            assert f'name="{field}"' not in body

        # Staff POST with base fields only still works and leaves owner settings untouched.
        ok_resp = self.staff_client.post(
            url,
            {
                "name": "Kost Kana",
                "address": "Jl. Kana Updated",
                "electricity_rate_per_kwh": "1550.00",
                "description": "Catatan",
            },
        )
        assert ok_resp.status_code == 302
        self.loc.refresh_from_db()
        assert self.loc.address == "Jl. Kana Updated"
        assert self.loc.billing_mode == KostLocation.BillingMode.SIMULTANEOUS

        # Staff tampering with any owner-only field returns 403.
        for field, val in (
            ("billing_mode", "per_room_cycle"),
            ("bills_electricity", "on"),
            ("bank_name", "Mandiri"),
            ("bank_account_number", "99999999"),
            ("bank_account_holder", "Penipu"),
        ):
            bad_resp = self.staff_client.post(
                url,
                {
                    "name": "Kost Kana",
                    "address": "Jl. Kana Updated",
                    "electricity_rate_per_kwh": "1550.00",
                    "description": "",
                    field: val,
                },
            )
            assert bad_resp.status_code == 403
        self.loc.refresh_from_db()
        assert self.loc.bank_account_number == ""
        assert self.loc.billing_mode == KostLocation.BillingMode.SIMULTANEOUS

        # Staff POST attempting owner fields on Django admin returns 403.
        change_perm = Permission.objects.get(codename="change_kostlocation")
        self.staff.user_permissions.add(change_perm)
        admin_url = reverse("admin:core_kostlocation_change", args=[self.loc.pk])
        admin_get = self.staff_client.get(admin_url)
        assert admin_get.status_code == 200
        admin_body = admin_get.content.decode("utf-8")
        for field in OWNER_ONLY_LOCATION_FIELDS:
            assert f'name="{field}"' not in admin_body
        admin_post = self.staff_client.post(
            admin_url,
            {
                "name": "Kost Kana",
                "address": "Jl. Kana Updated",
                "electricity_rate_per_kwh": "1550.00",
                "bank_account_number": "99999999",
            },
        )
        assert admin_post.status_code == 403
