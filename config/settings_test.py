"""Settings for the test suite only. Never used by a running server."""

import tempfile

from config.settings import *  # noqa: F403  (settings module re-export is the Django pattern)

# PBKDF2 at production strength costs ~0.3 s per password; the suite creates and logs in
# thousands of users. MD5 is acceptable here because no real password exists in tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

MEDIA_ROOT = tempfile.mkdtemp(prefix="ekm-test-media-")
