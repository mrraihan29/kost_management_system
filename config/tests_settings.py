"""Guards that test-only shortcuts never reach the production settings."""

import importlib


def test_production_settings_keep_django_default_password_hashers():
    prod = importlib.import_module("config.settings")
    assert not hasattr(prod, "PASSWORD_HASHERS"), (
        "config/settings.py must use Django's default (PBKDF2) hashers; "
        "the MD5 hasher belongs only in config/settings_test.py"
    )
