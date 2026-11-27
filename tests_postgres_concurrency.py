"""
PostgreSQL-only concurrency verification for the financial hardening (W1/W2).

These tests exercise REAL row-lock contention with independent connections and
transactions. They are skipped automatically on non-PostgreSQL backends because
`select_for_update()` is a no-op on SQLite.

Run with a disposable PostgreSQL instance, e.g.:

    docker run --name evykost-pg-concurrency -e POSTGRES_PASSWORD=... \
        -e POSTGRES_DB=evykost_concurrency -p 55433:5432 -d postgres:16-alpine

    set DATABASE_URL=postgres://postgres:<pw>@127.0.0.1:55433/evykost_concurrency
    python manage.py test tests_postgres_concurrency --verbosity 2

Synchronization strategy: the "winner" thread is deterministic. A narrow seam
(`timezone.now` for decisions, `Payment.save` for uploads) sleeps once INSIDE
the winner's atomic block, after the row locks are acquired, while an Event
signals the main thread. The main thread then starts the loser and observes an
ungranted lock in `pg_locks` — proving the competing transaction is actually
waiting on the row lock — before the winner commits.
"""

import io
import tempfile
import threading
import time
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock, skipUnless

from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse
from PIL import Image

from core.models import KostLocation, Room
from finance.models import ElectricityReading, Invoice, Payment
from tenants.models import Tenant, TenantContract
from users.models import AdminProfile, User

# Mirror the simulation suite: no manifest hashing, isolated media writes
MEDIA_ROOT_TMP = tempfile.mkdtemp()


def _image_buffer(name="pg_proof.jpg"):
    image = Image.new("RGB", (20, 20), color="blue")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    buffer.seek(0)
    buffer.name = name
    return buffer


def _wait_for_waiting_lock(timeout=8.0):
    """True when PostgreSQL reports an ACTIVE backend blocked on a lock wait."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_locks l "
                "JOIN pg_stat_activity a ON a.pid = l.pid "
                "WHERE NOT l.granted AND a.wait_event_type = 'Lock'"
            )
            if cursor.fetchone()[0] > 0:
                return True
        time.sleep(0.05)
    return False


@override_settings(
    MEDIA_ROOT=MEDIA_ROOT_TMP,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
@skipUnless(connection.vendor == "postgresql", "Real PostgreSQL required for row-lock contention")
class PostgresConcurrencyTests(TransactionTestCase):
    """Independent-connection contention tests (no SQLite no-ops, no fakes)."""

    def setUp(self):
        self.location = KostLocation.objects.create(
            name="PG Ancol", address="x", electricity_rate_per_kwh=Decimal("1500")
        )
        self.room = Room.objects.create(
            kost_location=self.location, room_number="A-1", price_monthly=Decimal("1500000")
        )
        self.staff = User.objects.create_user(username="pg_staff", password="x", is_staff=True)
        AdminProfile.objects.create(user=self.staff, assigned_location=self.location)
        self.tenant = Tenant.objects.create(
            full_name="PG Tenant", phone_number="081", emergency_contact_phone="082"
        )
        self.contract = TenantContract.objects.create(
            tenant=self.tenant,
            room=self.room,
            start_date=date.today(),
            monthly_rent_amount=Decimal("1500000"),
        )

    # ---------- helpers ----------

    def _fresh_contract(self, suffix):
        """A new tenant + room + contract; lets each round create a distinct invoice period."""
        tenant = Tenant.objects.create(
            full_name=f"PG Tenant {suffix}", phone_number="081", emergency_contact_phone="082"
        )
        room = Room.objects.create(
            kost_location=self.location, room_number=f"A-{suffix}", price_monthly=Decimal("1500000")
        )
        return TenantContract.objects.create(
            tenant=tenant,
            room=room,
            start_date=date.today(),
            monthly_rent_amount=Decimal("1500000"),
        )

    def _invoice(self, status="MENUNGGU_VERIFIKASI", contract=None):
        return Invoice.objects.create(
            contract=contract or self.contract,
            billing_period_start=date.today().replace(day=1),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal("1500000"),
            electricity_bill_amount=0,
            status=status,
        )

    def _payment(self, invoice):
        return Payment.objects.create(invoice=invoice, payment_proof_file="payment_proofs/pg.jpg")

    def _staff_client(self):
        client = Client()
        client.force_login(self.staff)
        return client

    def _public_client(self, contract=None):
        client = Client()
        session = client.session
        session["verified_contract_id"] = (contract or self.contract).id
        session.save()
        return client

    def _run_thread(self, fn, results, key):
        def runner():
            try:
                results[key] = fn()
            except Exception as exc:  # surfaced for assertions, never swallowed
                results[key] = exc
            finally:
                connections.close_all()

        thread = threading.Thread(target=runner)
        thread.start()
        return thread

    def _slow_payment_save(self, slow_ident, entered, hold=2.0):
        """Payment.save seam: signal + hold the winner's txn after locks are taken.

        verify_payment saves the locked payment INSIDE its atomic block (after both
        row locks), and public_payment_step2 inserts the payment after its invoice
        lock — both precede commit, so this seam always fires while locks are held.
        """
        real_save = Payment.save

        def wrapper(self_object, *args, **kwargs):
            if threading.get_ident() == slow_ident.get("id") and not entered.is_set():
                entered.set()
                time.sleep(hold)
            return real_save(self_object, *args, **kwargs)

        return mock.patch.object(Payment, "save", wrapper)

    def _assert_clean(self, results, *keys):
        for key in keys:
            self.assertNotIsInstance(
                results.get(key), Exception, f"{key} raised: {results.get(key)!r}"
            )

    # ---------- PG-1: concurrent payment decisions ----------

    def test_pg1a_approve_wins_reject_serializes_zero_write(self):
        invoice = self._invoice()
        payment = self._payment(invoice)
        results, guard_errors = {}, []
        slow_ident, entered = {}, threading.Event()
        loser_ident = {}

        def record_error(request, message, *args, **kwargs):
            guard_errors.append((threading.get_ident(), str(message)))

        def approve():
            slow_ident["id"] = threading.get_ident()
            return self._staff_client().post(
                reverse("verify_payment", args=[payment.pk, "approve"])
            )

        def reject():
            loser_ident["id"] = threading.get_ident()
            return self._staff_client().post(
                reverse("verify_payment", args=[payment.pk, "reject"]),
                {"rejection_note": "loser attempt"},
            )

        with (
            self._slow_payment_save(slow_ident, entered),
            mock.patch("finance.views.messages.error", side_effect=record_error),
        ):
            winner = self._run_thread(approve, results, "approve")
            self.assertTrue(entered.wait(timeout=10), "winner never reached the lock-holding seam")
            loser = self._run_thread(reject, results, "reject")
            self.assertTrue(
                _wait_for_waiting_lock(timeout=8), "competing request did not wait on a row lock"
            )
            # Mid-race evidence: the winner holds the locks, DB still shows the pre-decision state
            payment.refresh_from_db()
            self.assertEqual(payment.status, "PENDING")
            winner.join(timeout=30)
            loser.join(timeout=30)

        self._assert_clean(results, "approve", "reject")
        self.assertEqual(results["approve"].status_code, 302)
        self.assertEqual(results["reject"].status_code, 302)
        self.assertTrue(guard_errors, "loser never hit the in-transaction guard")
        self.assertIn(loser_ident["id"], [ident for ident, _ in guard_errors])
        invoice.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(invoice.status, "LUNAS")
        self.assertEqual(payment.status, "APPROVED")
        self.assertEqual(payment.verified_by, self.staff)
        self.assertIsNotNone(payment.verified_at)
        self.assertIsNone(payment.rejection_note)  # loser performed zero writes

    def test_pg1b_reject_wins_approve_serializes_zero_write(self):
        invoice = self._invoice()
        payment = self._payment(invoice)
        results, guard_errors = {}, []
        slow_ident, entered = {}, threading.Event()
        loser_ident = {}

        def record_error(request, message, *args, **kwargs):
            guard_errors.append((threading.get_ident(), str(message)))

        def reject():
            slow_ident["id"] = threading.get_ident()
            return self._staff_client().post(
                reverse("verify_payment", args=[payment.pk, "reject"]),
                {"rejection_note": "winner rejection"},
            )

        def approve():
            loser_ident["id"] = threading.get_ident()
            return self._staff_client().post(
                reverse("verify_payment", args=[payment.pk, "approve"])
            )

        with (
            self._slow_payment_save(slow_ident, entered),
            mock.patch("finance.views.messages.error", side_effect=record_error),
        ):
            winner = self._run_thread(reject, results, "reject")
            self.assertTrue(entered.wait(timeout=10), "winner never reached the lock-holding seam")
            loser = self._run_thread(approve, results, "approve")
            self.assertTrue(
                _wait_for_waiting_lock(timeout=8), "competing request did not wait on a row lock"
            )
            payment.refresh_from_db()
            self.assertEqual(payment.status, "PENDING")
            winner.join(timeout=30)
            loser.join(timeout=30)

        self._assert_clean(results, "reject", "approve")
        self.assertEqual(results["reject"].status_code, 302)
        self.assertEqual(results["approve"].status_code, 302)
        self.assertTrue(guard_errors, "loser never hit the in-transaction guard")
        self.assertIn(loser_ident["id"], [ident for ident, _ in guard_errors])
        invoice.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(payment.status, "REJECTED")
        self.assertEqual(payment.rejection_note, "winner rejection")
        self.assertNotEqual(invoice.status, "LUNAS")  # loser did not mark it paid
        self.assertEqual(invoice.status, "BELUM_LUNAS")  # due date in the future

    # ---------- PG-2: electricity write vs finalization ----------

    def test_pg2a_electricity_view_waits_then_is_refused(self):
        invoice = self._invoice()  # MENUNGGU_VERIFIKASI
        payment = self._payment(invoice)
        results = {}
        slow_ident, entered = {}, threading.Event()

        def approve():
            slow_ident["id"] = threading.get_ident()
            return self._staff_client().post(
                reverse("verify_payment", args=[payment.pk, "approve"])
            )

        def electricity():
            return self._staff_client().post(
                reverse("invoice_detail", args=[invoice.pk]),
                {"meter_reading_start": 0, "meter_reading_end": 100, "rate_per_kwh": "1500.00"},
            )

        with self._slow_payment_save(slow_ident, entered):
            winner = self._run_thread(approve, results, "approve")
            self.assertTrue(entered.wait(timeout=10))
            loser = self._run_thread(electricity, results, "electricity")
            self.assertTrue(
                _wait_for_waiting_lock(timeout=8),
                "electricity writer did not wait on the invoice lock",
            )
            winner.join(timeout=30)
            loser.join(timeout=30)

        self._assert_clean(results, "approve", "electricity")
        self.assertEqual(results["electricity"].status_code, 302)  # refused after lock release
        self.assertFalse(ElectricityReading.objects.filter(invoice=invoice).exists())
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "LUNAS")
        self.assertEqual(invoice.electricity_bill_amount, Decimal("0"))
        self.assertEqual(invoice.total_amount, Decimal("1500000.00"))

    def test_pg2b_electricity_model_save_waits_then_raises_validation(self):
        invoice = self._invoice()
        payment = self._payment(invoice)
        results = {}
        slow_ident, entered = {}, threading.Event()

        def approve():
            slow_ident["id"] = threading.get_ident()
            return self._staff_client().post(
                reverse("verify_payment", args=[payment.pk, "approve"])
            )

        def model_write():
            reading = ElectricityReading(
                invoice_id=invoice.pk,
                meter_reading_start=0,
                meter_reading_end=10,
                rate_per_kwh=Decimal("1500"),
            )
            try:
                reading.save()
                return "saved"
            except ValidationError as exc:
                return ("validation", str(exc))

        with self._slow_payment_save(slow_ident, entered):
            winner = self._run_thread(approve, results, "approve")
            self.assertTrue(entered.wait(timeout=10))
            loser = self._run_thread(model_write, results, "model_write")
            self.assertTrue(
                _wait_for_waiting_lock(timeout=8), "model save did not wait on the invoice lock"
            )
            winner.join(timeout=30)
            loser.join(timeout=30)

        self._assert_clean(results, "approve", "model_write")
        self.assertEqual(results["model_write"][0], "validation")
        self.assertFalse(ElectricityReading.objects.filter(invoice=invoice).exists())
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "LUNAS")
        self.assertEqual(invoice.electricity_bill_amount, Decimal("0"))

    # ---------- PG-3: upload vs finalization / duplicate uploads ----------

    def test_pg3a_upload_cannot_write_against_finalized_invoice(self):
        invoice = self._invoice()
        payment = self._payment(invoice)
        results, guard_errors = {}, []
        slow_ident, entered = {}, threading.Event()
        loser_ident = {}

        def record_error(request, message, *args, **kwargs):
            guard_errors.append((threading.get_ident(), str(message)))

        def approve():
            slow_ident["id"] = threading.get_ident()
            return self._staff_client().post(
                reverse("verify_payment", args=[payment.pk, "approve"])
            )

        def upload():
            loser_ident["id"] = threading.get_ident()
            return self._public_client().post(
                reverse("public_payment_step2"),
                {"payment_proof_file": _image_buffer("pg_pg3a.jpg")},
                format="multipart",
            )

        with (
            self._slow_payment_save(slow_ident, entered),
            mock.patch("finance.views.messages.error", side_effect=record_error),
        ):
            winner = self._run_thread(approve, results, "approve")
            self.assertTrue(entered.wait(timeout=10))
            loser = self._run_thread(upload, results, "upload")
            winner.join(timeout=30)
            loser.join(timeout=30)

        self._assert_clean(results, "approve", "upload")
        # While the winner held the lock the invoice was still MENUNGGU_VERIFIKASI, so the
        # upload path saw no active invoice; after commit the state is LUNAS. Either way:
        self.assertEqual(results["upload"].status_code, 302)
        self.assertTrue(guard_errors, "upload was neither locked nor refused with a message")
        self.assertIn(loser_ident["id"], [ident for ident, _ in guard_errors])
        self.assertEqual(
            Payment.objects.filter(invoice=invoice).count(), 1
        )  # only the seed payment
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "LUNAS")
        self.assertEqual(invoice.total_amount, Decimal("1500000.00"))

    def test_pg3b_duplicate_upload_serializes_and_loser_writes_nothing(self):
        invoice = self._invoice(status="BELUM_LUNAS")
        results, guard_errors = {}, []
        slow_ident, entered = {}, threading.Event()
        loser_ident = {}

        def record_error(request, message, *args, **kwargs):
            guard_errors.append((threading.get_ident(), str(message)))

        real_save = Payment.save

        def slow_save(self_object, *args, **kwargs):
            if threading.get_ident() == slow_ident.get("id") and not entered.is_set():
                entered.set()
                time.sleep(2.0)
            return real_save(self_object, *args, **kwargs)

        def upload_first():
            slow_ident["id"] = threading.get_ident()
            return self._public_client().post(
                reverse("public_payment_step2"),
                {"payment_proof_file": _image_buffer("pg_pg3b_first.jpg")},
                format="multipart",
            )

        def upload_second():
            loser_ident["id"] = threading.get_ident()
            return self._public_client().post(
                reverse("public_payment_step2"),
                {"payment_proof_file": _image_buffer("pg_pg3b_second.jpg")},
                format="multipart",
            )

        with (
            mock.patch.object(Payment, "save", slow_save),
            mock.patch("finance.views.messages.error", side_effect=record_error),
        ):
            winner = self._run_thread(upload_first, results, "first")
            self.assertTrue(entered.wait(timeout=10), "winner never reached the upload seam")
            loser = self._run_thread(upload_second, results, "second")
            self.assertTrue(
                _wait_for_waiting_lock(timeout=8), "second upload did not wait on the invoice lock"
            )
            winner.join(timeout=30)
            loser.join(timeout=30)

        self._assert_clean(results, "first", "second")
        self.assertEqual(results["first"].status_code, 200)  # success page
        self.assertEqual(results["second"].status_code, 302)  # refused under lock
        self.assertTrue(guard_errors, "losing upload never hit the in-lock re-check")
        self.assertIn(loser_ident["id"], [ident for ident, _ in guard_errors])
        self.assertEqual(Payment.objects.filter(invoice=invoice).count(), 1)  # exactly one proof
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "MENUNGGU_VERIFIKASI")
        self.assertEqual(invoice.total_amount, Decimal("1500000.00"))  # stale totals never written

    # ---------- PG-4: deadlock sanity ----------

    def test_pg4_mixed_concurrent_flows_complete_without_deadlock(self):
        barrier = threading.Barrier(2)
        max_rounds = 4
        for round_index in range(max_rounds):
            contract = self._fresh_contract(f"decision-{round_index}")
            invoice = self._invoice(contract=contract)
            payment = self._payment(invoice)
            results = {}

            def approve(barrier=barrier, payment=payment):
                barrier.wait(timeout=10)
                return self._staff_client().post(
                    reverse("verify_payment", args=[payment.pk, "approve"])
                )

            def reject(barrier=barrier, payment=payment, round_index=round_index):
                barrier.wait(timeout=10)
                return self._staff_client().post(
                    reverse("verify_payment", args=[payment.pk, "reject"]),
                    {"rejection_note": f"round {round_index}"},
                )

            first = self._run_thread(approve, results, "approve")
            second = self._run_thread(reject, results, "reject")
            first.join(timeout=30)
            second.join(timeout=30)
            self._assert_clean(results, "approve", "reject")
            for key in ("approve", "reject"):
                error_text = str(results[key]).lower()
                self.assertNotIn("deadlock", error_text)
                self.assertEqual(results[key].status_code, 302)

            invoice.refresh_from_db()
            payment.refresh_from_db()
            approved_outcome = (
                invoice.status == "LUNAS"
                and payment.status == "APPROVED"
                and payment.rejection_note is None
            )
            rejected_outcome = (
                invoice.status in ("BELUM_LUNAS", "TELAT_BAYAR")
                and payment.status == "REJECTED"
                and bool(payment.rejection_note)
            )
            self.assertTrue(
                approved_outcome or rejected_outcome,
                f"round {round_index}: inconsistent outcome {invoice.status}/{payment.status}",
            )

        # Second representative pair: upload versus electricity on an unpaid invoice.
        contract = self._fresh_contract("mixed")
        invoice = self._invoice(status="BELUM_LUNAS", contract=contract)
        results = {}
        barrier2 = threading.Barrier(2)

        def upload(barrier=barrier2, contract=contract):
            barrier.wait(timeout=10)
            return self._public_client(contract).post(
                reverse("public_payment_step2"),
                {"payment_proof_file": _image_buffer("pg_pg4.jpg")},
                format="multipart",
            )

        def electricity(barrier=barrier2):
            barrier.wait(timeout=10)
            return self._staff_client().post(
                reverse("invoice_detail", args=[invoice.pk]),
                {"meter_reading_start": 0, "meter_reading_end": 100, "rate_per_kwh": "1500.00"},
            )

        first = self._run_thread(upload, results, "upload")
        second = self._run_thread(electricity, results, "electricity")
        first.join(timeout=30)
        second.join(timeout=30)
        self._assert_clean(results, "upload", "electricity")
        for key in ("upload", "electricity"):
            self.assertNotIn("deadlock", str(results[key]).lower())
        invoice.refresh_from_db()
        # Coherent outcome regardless of ordering: the upload cannot be refused while the
        # invoice is BELUM_LUNAS, so it always commits MENUNGGU; the electricity write either
        # landed first (reading present, counted in the total) or was refused under the lock.
        self.assertEqual(invoice.status, "MENUNGGU_VERIFIKASI")
        if ElectricityReading.objects.filter(invoice=invoice).exists():
            self.assertEqual(invoice.electricity_bill_amount, Decimal("150000.00"))
        else:
            self.assertEqual(invoice.electricity_bill_amount, Decimal("0"))
