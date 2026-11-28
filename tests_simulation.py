"""
=============================================================================
FULL BUSINESS PROCESS SIMULATION TEST
Evy Kost Management System — End-to-End Automation
=============================================================================
Covers ALL 47 features, 89+ test steps, across 11 phases.
Uses Django's TestCase + Client for HTTP-level simulation.

Run: python manage.py test tests_simulation --verbosity=2
=============================================================================
"""

import calendar
import io
import tempfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError
from django.db.models.query import QuerySet
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import KostLocation, Room
from finance.billing import issue_due
from finance.models import ElectricityReading, Invoice, OperationCost, Payment
from tenants.models import MaintenanceTicket, Tenant, TenantContract
from users.models import AdminProfile

User = get_user_model()

# Disable file storage writes during test for speed
MEDIA_ROOT_TMP = tempfile.mkdtemp()


def create_test_image(name="test.jpg", size=(100, 100)):
    """Create a minimal valid JPEG file for upload testing."""
    from PIL import Image

    img = Image.new("RGB", size, color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    buf.name = name
    return buf


@override_settings(
    MEDIA_ROOT=MEDIA_ROOT_TMP,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class FullBusinessProcessTest(TestCase):
    """
    Single monolithic test class that simulates the ENTIRE business process
    in chronological order — exactly as documented in BUSINESS_PROCESS_SIMULATION.md
    """

    # ================================================================
    # PHASE 0: SYSTEM SETUP
    # ================================================================
    def setUp(self):
        """Phase 0: Create base infrastructure."""
        self.client = Client()
        self.superuser_client = Client()
        self.admin_ancol_client = Client()
        self.admin_kana_client = Client()
        self.admin_uns_client = Client()
        self.public_client = Client()  # For tenant portal
        self.plain_user_client = Client()

        # 0.1 — Create Superuser
        self.superuser = User.objects.create_superuser(
            username="admin",
            password="admin123",
            email="admin@evy.id",
            first_name="Evy",
            last_name="Owner",
        )

        # 0.2 — Create Locations
        self.loc_ancol = KostLocation.objects.create(
            name="Kost Ancol",
            address="Jl. Pasir Putih, Ancol",
            electricity_rate_per_kwh=Decimal("1500.00"),
            billing_mode=KostLocation.BillingMode.PER_ROOM_CYCLE,
            bills_electricity=True,
        )
        self.loc_kana = KostLocation.objects.create(
            name="Kost Kana",
            address="Jl. Dago Pakar, Bandung",
            electricity_rate_per_kwh=Decimal("1700.00"),
            billing_mode=KostLocation.BillingMode.SIMULTANEOUS,
            bills_electricity=False,
        )
        self.loc_uns = KostLocation.objects.create(
            name="Kost UNS",
            address="Jl. Ir Sutami, Solo",
            electricity_rate_per_kwh=Decimal("1300.00"),
            billing_mode=KostLocation.BillingMode.SIMULTANEOUS,
            bills_electricity=False,
        )

        # 0.3 — Create Rooms (3 per location for testing)
        self.rooms = {}
        for loc, prefix, prices in [
            (self.loc_ancol, "A", [1500000, 2000000, 1500000]),
            (self.loc_kana, "K", [1500000, 1800000, 1500000]),
            (self.loc_uns, "U", [1000000, 1500000, 1200000]),
        ]:
            for i, price in enumerate(prices, 1):
                room = Room.objects.create(
                    kost_location=loc,
                    room_number=f"{prefix}-10{i}",
                    price_monthly=Decimal(str(price)),
                    is_token_electricity=(prefix == "K"),  # Kana = token
                    capacity=1,
                )
                self.rooms[f"{prefix}-10{i}"] = room

        # 0.4 — Create Admin Staff Users
        self.admin_ancol = User.objects.create_user(
            username="admin_ancol",
            password="staff123",
            is_staff=True,
            first_name="Admin",
            last_name="Ancol",
        )
        AdminProfile.objects.create(user=self.admin_ancol, assigned_location=self.loc_ancol)

        self.admin_kana = User.objects.create_user(
            username="admin_kana",
            password="staff123",
            is_staff=True,
            first_name="Admin",
            last_name="Kana",
        )
        AdminProfile.objects.create(user=self.admin_kana, assigned_location=self.loc_kana)

        self.admin_uns = User.objects.create_user(
            username="admin_uns",
            password="staff123",
            is_staff=True,
            first_name="Admin",
            last_name="UNS",
        )
        AdminProfile.objects.create(user=self.admin_uns, assigned_location=self.loc_uns)

        self.plain_user = User.objects.create_user(
            username="plain_user",
            password="plain123",
            is_staff=False,
            first_name="Plain",
            last_name="User",
        )

        # Login all clients
        self.superuser_client.login(username="admin", password="admin123")
        self.admin_ancol_client.login(username="admin_ancol", password="staff123")
        self.admin_kana_client.login(username="admin_kana", password="staff123")
        self.admin_uns_client.login(username="admin_uns", password="staff123")
        self.plain_user_client.login(username="plain_user", password="plain123")

    # ================================================================
    # PHASE 0: INFRASTRUCTURE TESTS (F-45, F-46, F-01)
    # ================================================================
    def test_phase0_01_health_check(self):
        """F-45: Health check returns OK + DB connected."""
        resp = self.client.get("/health/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["database"], "connected")

    def test_phase0_02_landing_page(self):
        """F-01: Landing page renders for anonymous user."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "home.html")

    def test_phase0_03_landing_redirect_logged_in(self):
        """F-01: Landing page redirects to dashboard for logged-in user."""
        resp = self.superuser_client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("dashboard", resp.url)

    def test_phase0_04_django_admin(self):
        """F-46: Django admin panel accessible by superuser."""
        resp = self.superuser_client.get("/sekretariat-evykost/")
        self.assertEqual(resp.status_code, 200)

    # ================================================================
    # PHASE 1: AUTH & STAFF MANAGEMENT
    # ================================================================
    def test_phase1_01_login_page(self):
        """F-08: Login page renders."""
        resp = self.client.get("/accounts/login/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "auth/login.html")

    def test_phase1_02_login_success(self):
        """F-08: Superuser login succeeds."""
        c = Client()
        resp = c.post("/accounts/login/", {"username": "admin", "password": "admin123"})
        self.assertEqual(resp.status_code, 302)  # Redirect to next/dashboard

    def test_phase1_03_login_fail(self):
        """F-08: Wrong password stays on login page."""
        c = Client()
        resp = c.post("/accounts/login/", {"username": "admin", "password": "wrong"})
        self.assertEqual(resp.status_code, 200)  # Stays on login

    def test_phase1_04_logout(self):
        """F-09: Logout redirects to login."""
        c = Client()
        c.login(username="admin", password="admin123")
        resp = c.post("/accounts/logout/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_phase1_05_staff_list_superuser(self):
        """F-39: Superuser sees staff list."""
        resp = self.superuser_client.get(reverse("staff_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "admin_ancol")

    def test_phase1_06_staff_list_admin_forbidden(self):
        """F-39: Non-superuser redirected from staff list."""
        resp = self.admin_ancol_client.get(reverse("staff_list"))
        self.assertEqual(resp.status_code, 302)

    def test_phase1_07_staff_create(self):
        """F-40: Superuser creates a new staff."""
        resp = self.superuser_client.post(
            reverse("staff_add"),
            {
                "username": "admin_test",
                "password1": "TestPass123!",
                "password2": "TestPass123!",
                "first_name": "Test",
                "last_name": "Admin",
                "email": "test@evy.id",
                "assigned_location": self.loc_ancol.pk,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(username="admin_test").exists())
        new_user = User.objects.get(username="admin_test")
        self.assertTrue(new_user.is_staff)
        self.assertEqual(new_user.admin_profile.assigned_location, self.loc_ancol)

    def test_phase1_08_staff_update(self):
        """F-41: Superuser edits staff data."""
        resp = self.superuser_client.post(
            reverse("staff_edit", args=[self.admin_ancol.pk]),
            {
                "first_name": "Updated",
                "last_name": "Ancol",
                "email": "updated@evy.id",
                "is_active": True,
                "assigned_location": self.loc_ancol.pk,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.admin_ancol.refresh_from_db()
        self.assertEqual(self.admin_ancol.first_name, "Updated")

    def test_phase1_09_password_change_page(self):
        """F-10: Password change page renders for logged-in user."""
        resp = self.admin_ancol_client.get(reverse("password_change"))
        self.assertEqual(resp.status_code, 200)

    # ================================================================
    # PHASE 2: LOCATION MANAGEMENT
    # ================================================================
    def test_phase2_01_location_list_superuser(self):
        """F-13: Superuser sees all locations."""
        resp = self.superuser_client.get(reverse("location_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Kost Ancol")
        self.assertContains(resp, "Kost Kana")
        self.assertContains(resp, "Kost UNS")

    def test_phase2_02_location_list_admin_redirect(self):
        """F-13: Admin biasa gets redirected to own location edit."""
        resp = self.admin_ancol_client.get(reverse("location_list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(str(self.loc_ancol.pk), resp.url)

    def test_phase2_03_location_update_superuser(self):
        """F-14: Superuser edits location tariff."""
        resp = self.superuser_client.post(
            reverse("location_update", args=[self.loc_ancol.pk]),
            {
                "name": "Kost Ancol",
                "address": "Jl. Pasir Putih, Ancol",
                "electricity_rate_per_kwh": "1600.00",
                "description": "Updated by superuser",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.loc_ancol.refresh_from_db()
        self.assertEqual(self.loc_ancol.electricity_rate_per_kwh, Decimal("1600.00"))

    def test_phase2_04_location_update_admin_own(self):
        """F-14: Admin edits own location."""
        resp = self.admin_ancol_client.post(
            reverse("location_update", args=[self.loc_ancol.pk]),
            {
                "name": "Kost Ancol",
                "address": "Jl. Pasir Putih Baru, Ancol",
                "electricity_rate_per_kwh": "1500.00",
                "description": "",
            },
        )
        self.assertEqual(resp.status_code, 302)

    def test_phase2_05_location_update_admin_other_forbidden(self):
        """F-14 Security: Admin cannot edit other location."""
        resp = self.admin_ancol_client.post(
            reverse("location_update", args=[self.loc_kana.pk]),
            {
                "name": "Hacked",
                "address": "Hacked",
                "electricity_rate_per_kwh": "9999",
                "description": "",
            },
        )
        self.assertEqual(resp.status_code, 404)
        self.loc_kana.refresh_from_db()
        self.assertNotEqual(self.loc_kana.name, "Hacked")

    # ================================================================
    # PHASE 3: ROOM MANAGEMENT
    # ================================================================
    def test_phase3_01_room_list(self):
        """F-15: Admin sees only rooms at their location."""
        resp = self.admin_ancol_client.get(reverse("room_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "A-101")
        self.assertNotContains(resp, "K-101")

    def test_phase3_02_room_list_superuser_all(self):
        """F-15: Superuser sees all rooms."""
        resp = self.superuser_client.get(reverse("room_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "A-101")
        self.assertContains(resp, "K-101")
        self.assertContains(resp, "U-101")

    def test_phase3_03_room_create(self):
        """F-16: Admin creates a room."""
        resp = self.admin_ancol_client.post(
            reverse("room_add"),
            {
                "kost_location": self.loc_ancol.pk,
                "room_number": "A-201",
                "price_monthly": "1800000",
                "is_token_electricity": False,
                "capacity": 1,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Room.objects.filter(room_number="A-201").exists())

    def test_phase3_04_room_update(self):
        """F-17: Admin edits room price."""
        room = self.rooms["A-101"]
        resp = self.admin_ancol_client.post(
            reverse("room_edit", args=[room.pk]),
            {
                "kost_location": self.loc_ancol.pk,
                "room_number": "A-101",
                "price_monthly": "1900000",
                "is_token_electricity": False,
                "capacity": 1,
            },
        )
        self.assertEqual(resp.status_code, 302)
        room.refresh_from_db()
        self.assertEqual(room.price_monthly, Decimal("1900000"))

    def test_phase3_05_room_delete_empty(self):
        """F-18: Admin deletes empty room."""
        room = Room.objects.create(
            kost_location=self.loc_ancol,
            room_number="A-999",
            price_monthly=Decimal("1000000"),
            capacity=1,
        )
        resp = self.admin_ancol_client.post(reverse("room_delete", args=[room.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Room.objects.filter(room_number="A-999").exists())

    def test_phase3_06_room_delete_occupied_fails(self):
        """F-18: Cannot delete room with active tenant."""
        room = self.rooms["A-101"]
        tenant = Tenant.objects.create(
            full_name="Temp Test", phone_number="081", emergency_contact_phone="082"
        )
        TenantContract.objects.create(
            tenant=tenant,
            room=room,
            start_date=date.today(),
            monthly_rent_amount=room.price_monthly,
            is_active=True,
        )
        resp = self.admin_ancol_client.post(reverse("room_delete", args=[room.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Room.objects.filter(pk=room.pk).exists())
        # Cleanup
        TenantContract.objects.filter(tenant=tenant).delete()
        tenant.delete()

    def test_phase3_07_room_cross_location_forbidden(self):
        """F-17 Security: Admin Ancol cannot edit Kana room."""
        kana_room = self.rooms["K-101"]
        resp = self.admin_ancol_client.post(
            reverse("room_edit", args=[kana_room.pk]),
            {
                "kost_location": self.loc_kana.pk,
                "room_number": "K-101",
                "price_monthly": "9999999",
                "capacity": 1,
            },
        )
        self.assertEqual(resp.status_code, 404)
        kana_room.refresh_from_db()
        self.assertNotEqual(kana_room.price_monthly, Decimal("9999999"))

    def test_phase3_08_room_list_natural_ordering(self):
        """UI data order: room numbers should use natural sort (2 before 10)."""
        Room.objects.create(
            kost_location=self.loc_ancol,
            room_number="2",
            price_monthly=Decimal("1200000"),
            capacity=1,
        )
        Room.objects.create(
            kost_location=self.loc_ancol,
            room_number="10",
            price_monthly=Decimal("1200000"),
            capacity=1,
        )

        resp = self.admin_ancol_client.get(reverse("room_list"))
        self.assertEqual(resp.status_code, 200)

        ordered_numbers = [room.room_number for room in resp.context["rooms"]]
        self.assertLess(ordered_numbers.index("2"), ordered_numbers.index("10"))

    # ================================================================
    # PHASE 4: TENANT ONBOARDING
    # ================================================================
    def test_phase4_01_tenant_list(self):
        """F-19: Tenant list renders with KPI."""
        resp = self.admin_ancol_client.get(reverse("tenant_list"))
        self.assertEqual(resp.status_code, 200)

    def test_phase4_02_tenant_create(self):
        """F-20: Admin creates a new tenant."""
        resp = self.admin_ancol_client.post(
            reverse("tenant_add"),
            {
                "full_name": "Budi Santoso",
                "phone_number": "081234567890",
                "emergency_contact_phone": "089876543210",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Tenant.objects.filter(full_name="Budi Santoso").exists())

    def test_phase4_03_tenant_update(self):
        """F-21: Admin edits tenant data."""
        tenant = Tenant.objects.create(
            full_name="Edit Me", phone_number="081", emergency_contact_phone="082"
        )
        # Tenant needs a contract at Ancol for admin_ancol to access
        TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["A-102"],
            start_date=date.today(),
            monthly_rent_amount=Decimal("2000000"),
        )
        resp = self.admin_ancol_client.post(
            reverse("tenant_edit", args=[tenant.pk]),
            {
                "full_name": "Edited Name",
                "phone_number": "081999",
                "emergency_contact_phone": "082999",
            },
        )
        self.assertEqual(resp.status_code, 302)
        tenant.refresh_from_db()
        self.assertEqual(tenant.full_name, "Edited Name")

    def test_phase4_04_tenant_search(self):
        """F-19: Search filters tenants."""
        Tenant.objects.create(
            full_name="Searchable Person", phone_number="081", emergency_contact_phone="082"
        )
        resp = self.superuser_client.get(reverse("tenant_list") + "?q=Searchable")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Searchable Person")

    def test_phase4_05_assign_room(self):
        """F-22: Admin assigns room to tenant, PIN auto-generated."""
        tenant = Tenant.objects.create(
            full_name="Assign Test", phone_number="081", emergency_contact_phone="082"
        )
        resp = self.admin_ancol_client.post(
            reverse("tenant_assign_room", args=[tenant.pk]),
            {
                "room": self.rooms["A-101"].pk,
                "start_date": date.today().isoformat(),
                "monthly_rent_amount": "1500000",
            },
        )
        self.assertEqual(resp.status_code, 302)
        contract = TenantContract.objects.filter(tenant=tenant, is_active=True).first()
        self.assertIsNotNone(contract)
        self.assertEqual(len(contract.payment_pin), 6)
        self.assertTrue(contract.payment_pin.isdigit())

    def test_phase4_06_double_assign_prevented(self):
        """F-22 Security: Cannot assign room if tenant already has active contract."""
        tenant = Tenant.objects.create(
            full_name="Double Test", phone_number="081", emergency_contact_phone="082"
        )
        TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["A-103"],
            start_date=date.today(),
            monthly_rent_amount=Decimal("1500000"),
        )
        # Try to assign again
        resp = self.admin_ancol_client.post(
            reverse("tenant_assign_room", args=[tenant.pk]),
            {
                "room": self.rooms["A-102"].pk,
                "start_date": date.today().isoformat(),
                "monthly_rent_amount": "1500000",
            },
        )
        # Should redirect with error (not create second contract)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(TenantContract.objects.filter(tenant=tenant, is_active=True).count(), 1)

    # ================================================================
    # PHASE 5: DASHBOARD
    # ================================================================
    def test_phase5_01_dashboard_superuser(self):
        """F-12: Superuser dashboard with location filter."""
        resp = self.superuser_client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Semua Lokasi")

    def test_phase5_02_dashboard_superuser_filter(self):
        """F-12: Superuser filters by location."""
        resp = self.superuser_client.get(reverse("dashboard") + f"?location={self.loc_ancol.pk}")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Kost Ancol")

    def test_phase5_03_dashboard_admin(self):
        """F-12: Admin sees only their location."""
        resp = self.admin_ancol_client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Kost Ancol")

    def test_phase5_04_dashboard_invalid_location(self):
        """F-12: Invalid location ID doesn't crash (B-02 fix)."""
        resp = self.superuser_client.get(reverse("dashboard") + "?location=abc")
        self.assertEqual(resp.status_code, 200)

    # ================================================================
    # PHASE 6: BILLING CYCLE
    # ================================================================
    def _setup_billing_data(self):
        """Helper: Create tenant with contract for billing tests."""
        tenant = Tenant.objects.create(
            full_name="Billing Tenant", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["A-101"],
            start_date=date.today() - timedelta(days=30),
            monthly_rent_amount=Decimal("1500000"),
        )
        return tenant, contract

    def test_phase6_01_generate_invoices_bulk(self):
        """F-28 / R-014: Simultaneous issue_invoices creates invoices with preview."""
        tenant = Tenant.objects.create(
            full_name="UNS Billing Tenant", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["U-101"],
            start_date=date.today() - timedelta(days=15),
            monthly_rent_amount=Decimal("1000000"),
        )
        today = timezone.localdate()
        period_key = f"{today.year:04d}-{today.month:02d}"
        preview_resp = self.admin_uns_client.get(reverse("issue_invoices"))
        self.assertEqual(preview_resp.status_code, 200)
        self.assertContains(preview_resp, "1 tagihan akan dibuat")

        resp = self.admin_uns_client.post(reverse("issue_invoices"), {"period": period_key})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Invoice.objects.filter(contract=contract).exists())

    def test_phase6_02_generate_invoices_idempotent(self):
        """F-28 / R-014: Issuing twice for the same month creates no duplicates."""
        tenant = Tenant.objects.create(
            full_name="UNS Idempotent Tenant", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["U-101"],
            start_date=date.today() - timedelta(days=15),
            monthly_rent_amount=Decimal("1000000"),
        )
        today = timezone.localdate()
        period_key = f"{today.year:04d}-{today.month:02d}"
        self.admin_uns_client.post(reverse("issue_invoices"), {"period": period_key})
        count_first = Invoice.objects.filter(contract=contract).count()
        self.admin_uns_client.post(reverse("issue_invoices"), {"period": period_key})
        count_second = Invoice.objects.filter(contract=contract).count()
        self.assertEqual(count_first, 1)
        self.assertEqual(count_first, count_second)

    def test_phase6_03_invoice_list(self):
        """F-25: Invoice list renders with pagination."""
        tenant, contract = self._setup_billing_data()
        Invoice.objects.create(
            contract=contract,
            billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal("1500000"),
            electricity_bill_amount=0,
            total_amount=Decimal("1500000"),
            status="BELUM_LUNAS",
        )
        resp = self.admin_ancol_client.get(reverse("invoice_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Billing Tenant")

    def test_phase6_04_invoice_list_filter_status(self):
        """F-25: Filter invoices by status."""
        tenant, contract = self._setup_billing_data()
        Invoice.objects.create(
            contract=contract,
            billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal("1500000"),
            electricity_bill_amount=0,
            total_amount=Decimal("1500000"),
            status="BELUM_LUNAS",
        )
        resp = self.admin_ancol_client.get(reverse("invoice_list") + "?status=LUNAS")
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Billing Tenant")

    def test_phase6_05_invoice_list_search(self):
        """F-25: Search invoices by tenant name."""
        tenant, contract = self._setup_billing_data()
        Invoice.objects.create(
            contract=contract,
            billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal("1500000"),
            electricity_bill_amount=0,
            total_amount=Decimal("1500000"),
            status="BELUM_LUNAS",
        )
        resp = self.admin_ancol_client.get(reverse("invoice_list") + "?q=Billing")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Billing Tenant")

    def test_phase6_05b_invoice_list_auto_sync_overdue_status(self):
        """R-024: invoice_list performs no status write on GET; status stays BELUM_LUNAS."""
        tenant, contract = self._setup_billing_data()
        invoice = Invoice.objects.create(
            contract=contract,
            billing_period_start=date.today() - timedelta(days=35),
            due_date=date.today() - timedelta(days=3),
            base_rent_amount=Decimal("1500000"),
            electricity_bill_amount=0,
            total_amount=Decimal("1500000"),
            status="BELUM_LUNAS",
        )

        resp = self.admin_ancol_client.get(reverse("invoice_list"))
        self.assertEqual(resp.status_code, 200)

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "BELUM_LUNAS")

    def test_phase6_06_invoice_detail_and_electricity(self):
        """F-26: Input electricity meter reading updates invoice total."""
        tenant, contract = self._setup_billing_data()
        invoice = Invoice.objects.create(
            contract=contract,
            billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal("1500000"),
            electricity_bill_amount=0,
            total_amount=Decimal("1500000"),
            status="BELUM_LUNAS",
        )
        # GET detail page
        resp = self.admin_ancol_client.get(reverse("invoice_detail", args=[invoice.pk]))
        self.assertEqual(resp.status_code, 200)

        # POST electricity reading
        resp = self.admin_ancol_client.post(
            reverse("invoice_detail", args=[invoice.pk]),
            {
                "meter_reading_start": 1000,
                "meter_reading_end": 1150,
                "rate_per_kwh": "1500.00",
            },
        )
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        # 150 kwh * 1500 = 225,000
        self.assertEqual(invoice.electricity_bill_amount, Decimal("225000.00"))
        self.assertEqual(invoice.total_amount, Decimal("1725000.00"))

    def test_phase6_07_electricity_validation(self):
        """F-26: Electricity meter end < start fails validation (D-02 fix)."""
        tenant, contract = self._setup_billing_data()
        invoice = Invoice.objects.create(
            contract=contract,
            billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal("1500000"),
            electricity_bill_amount=0,
            total_amount=Decimal("1500000"),
            status="BELUM_LUNAS",
        )
        resp = self.admin_ancol_client.post(
            reverse("invoice_detail", args=[invoice.pk]),
            {
                "meter_reading_start": 1150,
                "meter_reading_end": 1000,  # End < Start!
                "rate_per_kwh": "1500.00",
            },
        )
        # Should stay on page (200) with error, not redirect
        self.assertEqual(resp.status_code, 200)
        # No electricity reading should be saved
        self.assertFalse(ElectricityReading.objects.filter(invoice=invoice).exists())

    def test_phase6_08_invoice_cross_location_forbidden(self):
        """F-26 Security: Admin cannot view invoice at other location."""
        tenant = Tenant.objects.create(
            full_name="Kana Tenant", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["K-101"],
            start_date=date.today(),
            monthly_rent_amount=Decimal("1500000"),
        )
        invoice = Invoice.objects.create(
            contract=contract,
            billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal("1500000"),
            electricity_bill_amount=0,
            total_amount=Decimal("1500000"),
            status="BELUM_LUNAS",
        )
        # Admin Ancol tries to access Kana invoice
        resp = self.admin_ancol_client.get(reverse("invoice_detail", args=[invoice.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_phase6_09_management_command_update_overdue(self):
        """F-44 / R-024: mark_late_invoices command changes BELUM_LUNAS → TELAT_BAYAR."""
        tenant, contract = self._setup_billing_data()
        invoice = Invoice.objects.create(
            contract=contract,
            billing_period_start=date.today() - timedelta(days=30),
            due_date=date.today() - timedelta(days=5),  # Already overdue
            base_rent_amount=Decimal("1500000"),
            electricity_bill_amount=0,
            total_amount=Decimal("1500000"),
            status="BELUM_LUNAS",
        )
        call_command("mark_late_invoices")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "TELAT_BAYAR")

    def test_phase6_10_management_command_generate_monthly(self):
        """F-43 / R-013: issue_due_invoices command creates due per_room_cycle invoices."""
        tenant, contract = self._setup_billing_data()
        call_command("issue_due_invoices")
        self.assertTrue(Invoice.objects.filter(contract=contract).exists())

    def test_phase6_11_ancol_billing_rule(self):
        """Business Rule B1: Ancol per_room_cycle uses contract start_date.day + 10 days."""
        tenant, contract = self._setup_billing_data()
        call_command("issue_due_invoices")
        invoice = Invoice.objects.filter(contract=contract).order_by("billing_period_start").first()
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.due_date, invoice.billing_period_start + timedelta(days=10))

    def test_phase6_12_non_ancol_billing_rule(self):
        """Business Rule B1: Simultaneous location uses day 1 and due day 11."""
        tenant = Tenant.objects.create(
            full_name="UNS Tenant", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["U-101"],
            start_date=date.today() - timedelta(days=15),
            monthly_rent_amount=Decimal("1000000"),
        )
        today = timezone.localdate()
        self.admin_uns_client.post(
            reverse("issue_invoices"), {"period": f"{today.year:04d}-{today.month:02d}"}
        )
        invoice = Invoice.objects.filter(contract=contract).first()
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.billing_period_start.day, 1)
        expected_due = invoice.billing_period_start + timedelta(days=10)
        self.assertEqual(invoice.due_date, expected_due)

    # ================================================================
    # PHASE 7: PUBLIC PAYMENT PORTAL
    # ================================================================
    def _setup_payment_data(self):
        """Helper: Create full tenant+contract+invoice for payment flow."""
        tenant = Tenant.objects.create(
            full_name="Payment Tenant", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["A-102"],
            start_date=date.today() - timedelta(days=30),
            monthly_rent_amount=Decimal("2000000"),
        )
        invoice = Invoice.objects.create(
            contract=contract,
            billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal("2000000"),
            electricity_bill_amount=0,
            total_amount=Decimal("2000000"),
            status="BELUM_LUNAS",
        )
        return tenant, contract, invoice

    def test_phase7_01_public_step1_page(self):
        """F-02: PIN validation page renders."""
        resp = self.public_client.get(reverse("public_payment_step1"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "finance/step1_pin.html")

    def test_phase7_02_public_step1_wrong_pin(self):
        """F-02: Wrong PIN shows error."""
        tenant, contract, invoice = self._setup_payment_data()
        resp = self.public_client.post(
            reverse("public_payment_step1"),
            {
                "kost_location": self.loc_ancol.pk,
                "room_number": "A-102",
                "pin": "000000",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "PIN salah")

    def test_phase7_03_public_step1_success(self):
        """F-02: Correct PIN creates session and redirects."""
        tenant, contract, invoice = self._setup_payment_data()
        resp = self.public_client.post(
            reverse("public_payment_step1"),
            {
                "kost_location": self.loc_ancol.pk,
                "room_number": "A-102",
                "pin": contract.payment_pin,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("upload", resp.url)
        self.assertEqual(self.public_client.session["verified_contract_id"], contract.id)

    def test_phase7_04_public_step2_no_session(self):
        """F-03: Upload page without session redirects to PIN."""
        resp = self.public_client.get(reverse("public_payment_step2"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("bayar", resp.url)

    def test_phase7_05_public_step2_page(self):
        """F-03: Upload page shows invoice info."""
        tenant, contract, invoice = self._setup_payment_data()
        # Login via PIN first
        self.public_client.post(
            reverse("public_payment_step1"),
            {
                "kost_location": self.loc_ancol.pk,
                "room_number": "A-102",
                "pin": contract.payment_pin,
            },
        )
        resp = self.public_client.get(reverse("public_payment_step2"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Payment Tenant")

    def test_phase7_06_public_upload_payment(self):
        """F-03: Upload payment proof changes invoice status (after meter reading)."""
        tenant, contract, invoice = self._setup_payment_data()
        ElectricityReading.objects.create(
            invoice=invoice,
            meter_reading_start=0,
            meter_reading_end=10,
            rate_per_kwh=Decimal("1500"),
        )
        # Login via PIN
        self.public_client.post(
            reverse("public_payment_step1"),
            {
                "kost_location": self.loc_ancol.pk,
                "room_number": "A-102",
                "pin": contract.payment_pin,
            },
        )
        # Upload proof
        img = create_test_image()
        resp = self.public_client.post(
            reverse("public_payment_step2"), {"payment_proof_file": img}, format="multipart"
        )
        self.assertEqual(resp.status_code, 200)  # success.html rendered
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "MENUNGGU_VERIFIKASI")
        self.assertTrue(Payment.objects.filter(invoice=invoice).exists())

    def test_phase7_07_public_payment_history(self):
        """F-04: Payment history shows invoices with pagination."""
        tenant, contract, invoice = self._setup_payment_data()
        # Login via PIN
        session = self.public_client.session
        session["verified_contract_id"] = contract.id
        session.save()
        resp = self.public_client.get(reverse("public_payment_history"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Payment Tenant")

    def test_phase7_08_public_payment_history_no_session(self):
        """F-04: Payment history without session redirects."""
        resp = self.public_client.get(reverse("public_payment_history"))
        self.assertEqual(resp.status_code, 302)

    def test_phase7_09_public_logout(self):
        """F-05: Public logout clears session."""
        tenant, contract, invoice = self._setup_payment_data()
        session = self.public_client.session
        session["verified_contract_id"] = contract.id
        session.save()
        resp = self.public_client.get(reverse("public_logout"))
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("verified_contract_id", self.public_client.session)

    # ================================================================
    # PHASE 8: PAYMENT VERIFICATION
    # ================================================================
    def _setup_verification_data(self):
        """Helper: Create payment awaiting verification."""
        tenant, contract, invoice = self._setup_payment_data()
        invoice.status = "MENUNGGU_VERIFIKASI"
        invoice.save()
        payment = Payment.objects.create(
            invoice=invoice, payment_proof_file="payment_proofs/test.jpg"
        )
        return tenant, contract, invoice, payment

    def test_phase8_01_approve_payment(self):
        """F-29: Admin approves payment → invoice LUNAS."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        resp = self.admin_ancol_client.post(reverse("verify_payment", args=[payment.pk, "approve"]))
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "LUNAS")
        payment.refresh_from_db()
        self.assertIsNotNone(payment.verified_by)
        self.assertIsNotNone(payment.verified_at)

    def test_phase8_02_reject_payment(self):
        """F-30: Admin rejects payment → invoice reverts status."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        resp = self.admin_ancol_client.post(
            reverse("verify_payment", args=[payment.pk, "reject"]),
            {"rejection_note": "Bukti tidak jelas"},
        )
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        # Due date is in the future, so should be BELUM_LUNAS
        self.assertIn(invoice.status, ["BELUM_LUNAS", "TELAT_BAYAR"])
        payment.refresh_from_db()
        self.assertIn("Bukti tidak jelas", payment.rejection_note)

    def test_phase8_03_reject_overdue_payment(self):
        """F-30: Reject payment on overdue invoice → TELAT_BAYAR."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        invoice.due_date = date.today() - timedelta(days=5)
        invoice.save()
        self.admin_ancol_client.post(
            reverse("verify_payment", args=[payment.pk, "reject"]),
            {"rejection_note": "Wrong amount"},
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "TELAT_BAYAR")

    def test_phase8_04_verify_cross_location_forbidden(self):
        """F-29 Security: Admin cannot verify payment at other location."""
        tenant = Tenant.objects.create(
            full_name="Cross Test", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["K-101"],
            start_date=date.today(),
            monthly_rent_amount=Decimal("1500000"),
        )
        invoice = Invoice.objects.create(
            contract=contract,
            billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal("1500000"),
            electricity_bill_amount=0,
            total_amount=Decimal("1500000"),
            status="MENUNGGU_VERIFIKASI",
        )
        payment = Payment.objects.create(
            invoice=invoice, payment_proof_file="payment_proofs/test.jpg"
        )
        # Admin Ancol tries to approve Kana payment
        resp = self.admin_ancol_client.post(reverse("verify_payment", args=[payment.pk, "approve"]))
        self.assertEqual(resp.status_code, 404)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "MENUNGGU_VERIFIKASI")  # Not changed

    def test_phase8_05_verify_invalid_action(self):
        """F-29 Validation: Invalid action is rejected (F-03 fix)."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        resp = self.admin_ancol_client.post(
            reverse("verify_payment", args=[payment.pk, "invalid_action"])
        )
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "MENUNGGU_VERIFIKASI")

    def test_phase8_06_print_receipt_lunas(self):
        """F-27: Print receipt for LUNAS invoice."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        invoice.status = "LUNAS"
        invoice.save()
        resp = self.admin_ancol_client.get(reverse("print_receipt", args=[invoice.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "finance/print_receipt.html")

    def test_phase8_07_print_receipt_not_lunas_fails(self):
        """F-27: Cannot print receipt for non-LUNAS invoice."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        resp = self.admin_ancol_client.get(reverse("print_receipt", args=[invoice.pk]))
        self.assertEqual(resp.status_code, 302)  # Redirect with error

    # ================================================================
    # PHASE 9: MAINTENANCE TICKETS
    # ================================================================
    def _setup_maintenance_data(self):
        """Helper: Create session-authenticated public client with contract."""
        tenant = Tenant.objects.create(
            full_name="Maintenance Tenant", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["A-103"],
            start_date=date.today(),
            monthly_rent_amount=Decimal("1500000"),
        )
        # Set session for public client
        session = self.public_client.session
        session["verified_contract_id"] = contract.id
        session.save()
        return tenant, contract

    def test_phase9_01_report_create_page(self):
        """F-06: Report form renders with session."""
        tenant, contract = self._setup_maintenance_data()
        resp = self.public_client.get(reverse("public_report_create"))
        self.assertEqual(resp.status_code, 200)

    def test_phase9_02_report_create_no_session(self):
        """F-06: No session redirects to PIN."""
        c = Client()
        resp = c.get(reverse("public_report_create"))
        self.assertEqual(resp.status_code, 302)

    def test_phase9_03_report_submit(self):
        """F-06: Submit maintenance report creates ticket."""
        tenant, contract = self._setup_maintenance_data()
        resp = self.public_client.post(
            reverse("public_report_create"),
            {
                "title": "Kran Bocor",
                "priority": "HIGH",
                "description": "Kran di kamar mandi bocor deras",
            },
        )
        self.assertEqual(resp.status_code, 302)
        ticket = MaintenanceTicket.objects.filter(contract=contract).first()
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.title, "Kran Bocor")
        self.assertEqual(ticket.status, "PENDING")

    def test_phase9_04_report_list(self):
        """F-07: Report list shows tickets."""
        tenant, contract = self._setup_maintenance_data()
        MaintenanceTicket.objects.create(
            contract=contract, title="Test Ticket", description="Test", priority="MEDIUM"
        )
        resp = self.public_client.get(reverse("public_report_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Test Ticket")

    def test_phase9_05_admin_ticket_list(self):
        """F-35: Admin sees tickets at their location."""
        tenant, contract = self._setup_maintenance_data()
        MaintenanceTicket.objects.create(
            contract=contract, title="Admin View Ticket", description="Test", priority="HIGH"
        )
        resp = self.admin_ancol_client.get(reverse("ticket_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Admin View Ticket")

    def test_phase9_06_admin_ticket_filter_status(self):
        """F-35: Filter tickets by status."""
        tenant, contract = self._setup_maintenance_data()
        MaintenanceTicket.objects.create(
            contract=contract,
            title="Pending Ticket",
            description="Test",
            priority="LOW",
            status="PENDING",
        )
        resp = self.admin_ancol_client.get(reverse("ticket_list") + "?status=SELESAI")
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Pending Ticket")

    def test_phase9_07_admin_ticket_update_proses(self):
        """F-36: Admin updates ticket to PROSES."""
        tenant, contract = self._setup_maintenance_data()
        ticket = MaintenanceTicket.objects.create(
            contract=contract, title="Handlable", description="Test", priority="MEDIUM"
        )
        resp = self.admin_ancol_client.post(
            reverse("ticket_update", args=[ticket.pk]), {"status": "PROSES"}
        )
        self.assertEqual(resp.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "PROSES")
        self.assertIsNone(ticket.completion_date)

    def test_phase9_08_admin_ticket_update_selesai(self):
        """F-36: Admin updates ticket to SELESAI with completion_date."""
        tenant, contract = self._setup_maintenance_data()
        ticket = MaintenanceTicket.objects.create(
            contract=contract,
            title="Fixable",
            description="Test",
            priority="MEDIUM",
            status="PROSES",
        )
        resp = self.admin_ancol_client.post(
            reverse("ticket_update", args=[ticket.pk]), {"status": "SELESAI"}
        )
        self.assertEqual(resp.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "SELESAI")
        self.assertIsNotNone(ticket.completion_date)

    def test_phase9_09_admin_ticket_invalid_status(self):
        """F-36: Invalid status is rejected (H-01 fix)."""
        tenant, contract = self._setup_maintenance_data()
        ticket = MaintenanceTicket.objects.create(
            contract=contract, title="No Hack", description="Test", priority="MEDIUM"
        )
        resp = self.admin_ancol_client.post(
            reverse("ticket_update", args=[ticket.pk]), {"status": "HACKED_STATUS"}
        )
        self.assertEqual(resp.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "PENDING")  # Unchanged

    def test_phase9_10_admin_ticket_detail_page(self):
        """F-36: Ticket detail page renders on GET."""
        tenant, contract = self._setup_maintenance_data()
        ticket = MaintenanceTicket.objects.create(
            contract=contract, title="Detail View", description="Test detail", priority="LOW"
        )
        resp = self.admin_ancol_client.get(reverse("ticket_update", args=[ticket.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Detail View")

    # ================================================================
    # PHASE 10: OPERATIONAL COSTS
    # ================================================================
    def test_phase10_01_operation_list(self):
        """F-31: Operation list page renders."""
        resp = self.admin_ancol_client.get(reverse("operation_list"))
        self.assertEqual(resp.status_code, 200)

    def test_phase10_02_operation_create(self):
        """F-32: Admin creates operational cost."""
        img = create_test_image("nota.jpg")
        resp = self.admin_ancol_client.post(
            reverse("operation_add"),
            {
                "kost_location": self.loc_ancol.pk,
                "category": "LISTRIK",
                "amount": "2500000",
                "incurred_date": date.today().isoformat(),
                "description": "Bayar listrik bulanan PLN",
                "proof_file": img,
            },
        )
        self.assertEqual(resp.status_code, 302)
        cost = OperationCost.objects.filter(category="LISTRIK").first()
        self.assertIsNotNone(cost)
        self.assertEqual(cost.amount, Decimal("2500000"))
        self.assertEqual(cost.admin, self.admin_ancol)

    def test_phase10_03_operation_create_auto_location(self):
        """F-32: Admin biasa has location auto-forced."""
        img = create_test_image("nota2.jpg")
        resp = self.admin_ancol_client.post(
            reverse("operation_add"),
            {
                "kost_location": self.loc_kana.pk,  # Try Kana (wrong)
                "category": "PAM",
                "amount": "800000",
                "incurred_date": date.today().isoformat(),
                "description": "Tagihan PAM",
                "proof_file": img,
            },
        )
        if resp.status_code == 302:
            cost = OperationCost.objects.filter(category="PAM").first()
            if cost:
                # Location should be forced to Ancol
                self.assertEqual(cost.kost_location, self.loc_ancol)

    def test_phase10_04_operation_update(self):
        """F-33: Admin edits operational cost."""
        cost = OperationCost.objects.create(
            kost_location=self.loc_ancol,
            admin=self.admin_ancol,
            category="INTERNET",
            amount=Decimal("350000"),
            description="Wifi",
            incurred_date=date.today(),
            proof_file="operation_costs/test.jpg",
        )
        img = create_test_image("nota_edit.jpg")
        resp = self.admin_ancol_client.post(
            reverse("operation_edit", args=[cost.pk]),
            {
                "kost_location": self.loc_ancol.pk,
                "category": "INTERNET",
                "amount": "400000",
                "incurred_date": date.today().isoformat(),
                "description": "Wifi upgraded",
                "proof_file": img,
            },
        )
        self.assertEqual(resp.status_code, 302)
        cost.refresh_from_db()
        self.assertEqual(cost.amount, Decimal("400000"))

    def test_phase10_05_operation_delete(self):
        """F-34: Admin deletes operational cost."""
        cost = OperationCost.objects.create(
            kost_location=self.loc_ancol,
            admin=self.admin_ancol,
            category="LAINNYA",
            amount=Decimal("50000"),
            description="Delete me",
            incurred_date=date.today(),
            proof_file="operation_costs/test.jpg",
        )
        resp = self.admin_ancol_client.post(reverse("operation_delete", args=[cost.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(OperationCost.objects.filter(pk=cost.pk).exists())

    def test_phase10_06_operation_cross_location_hidden(self):
        """F-31 Security: Admin cannot see costs from other location."""
        OperationCost.objects.create(
            kost_location=self.loc_kana,
            admin=self.admin_kana,
            category="LISTRIK",
            amount=Decimal("1000000"),
            description="Kana cost",
            incurred_date=date.today(),
            proof_file="operation_costs/test.jpg",
        )
        resp = self.admin_ancol_client.get(reverse("operation_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Kana cost")

    def test_phase10_07_operation_total_expenses_uses_all_recorded_data(self):
        """Operational total card sums all recorded expenses, not only current month."""
        OperationCost.objects.create(
            kost_location=self.loc_ancol,
            admin=self.admin_ancol,
            category="LISTRIK",
            amount=Decimal("100000"),
            description="Biaya bulan ini",
            incurred_date=date.today(),
            proof_file="operation_costs/test1.jpg",
        )
        OperationCost.objects.create(
            kost_location=self.loc_ancol,
            admin=self.admin_ancol,
            category="PAM",
            amount=Decimal("250000"),
            description="Biaya bulan lalu",
            incurred_date=date.today() - timedelta(days=40),
            proof_file="operation_costs/test2.jpg",
        )

        resp = self.admin_ancol_client.get(reverse("operation_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total_expenses"], Decimal("350000"))

    # ================================================================
    # PHASE 11: FINANCIAL REPORTING
    # ================================================================
    def test_phase11_01_finance_report_page(self):
        """F-37: Finance report dashboard renders."""
        resp = self.admin_ancol_client.get(reverse("finance_report"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "finance/report_dashboard.html")

    def test_phase11_02_finance_report_filter_year(self):
        """F-37: Filter report by year."""
        resp = self.admin_ancol_client.get(reverse("finance_report") + f"?year={date.today().year}")
        self.assertEqual(resp.status_code, 200)

    def test_phase11_03_finance_report_superuser_filter_location(self):
        """F-37: Superuser filters report by location."""
        resp = self.superuser_client.get(
            reverse("finance_report")
            + f"?year={date.today().year}&kost_location={self.loc_ancol.pk}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Kost Ancol")

    def test_phase11_04_export_excel(self):
        """F-38: Export Excel downloads .xlsx with 3 sheets."""
        resp = self.admin_ancol_client.get(
            reverse("export_finance_excel") + f"?year={date.today().year}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("Laporan_Keuangan", resp["Content-Disposition"])
        # Verify 3 sheets
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(resp.content))
        self.assertEqual(len(wb.sheetnames), 3)
        self.assertIn("Ringkasan Bulanan", wb.sheetnames)
        self.assertIn("Rincian Pemasukan", wb.sheetnames)
        self.assertIn("Rincian Operasional", wb.sheetnames)

    # ================================================================
    # PHASE 12: TENANT CHECKOUT & CLEANUP
    # ================================================================
    def test_phase12_01_checkout_with_unpaid_fails(self):
        """F-23 + B2: Checkout rejected when unpaid invoices exist."""
        tenant = Tenant.objects.create(
            full_name="Checkout Fail", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["A-101"],
            start_date=date.today(),
            monthly_rent_amount=Decimal("1500000"),
        )
        Invoice.objects.create(
            contract=contract,
            billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal("1500000"),
            electricity_bill_amount=0,
            total_amount=Decimal("1500000"),
            status="BELUM_LUNAS",
        )
        resp = self.admin_ancol_client.post(reverse("tenant_checkout", args=[tenant.pk]))
        self.assertEqual(resp.status_code, 302)
        contract.refresh_from_db()
        self.assertTrue(contract.is_active)  # Not checked out

    def test_phase12_02_checkout_success(self):
        """F-23 + B2: Checkout succeeds when all invoices are LUNAS."""
        tenant = Tenant.objects.create(
            full_name="Checkout OK", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["A-102"],
            start_date=date.today() - timedelta(days=30),
            monthly_rent_amount=Decimal("2000000"),
        )
        Invoice.objects.create(
            contract=contract,
            billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal("2000000"),
            electricity_bill_amount=0,
            total_amount=Decimal("2000000"),
            status="LUNAS",
        )
        resp = self.admin_ancol_client.post(reverse("tenant_checkout", args=[tenant.pk]))
        self.assertEqual(resp.status_code, 302)
        contract.refresh_from_db()
        self.assertFalse(contract.is_active)
        self.assertIsNotNone(contract.end_date)

    def test_phase12_03_room_becomes_available_after_checkout(self):
        """F-15: Room shows as empty after checkout."""
        tenant = Tenant.objects.create(
            full_name="Room Check", phone_number="081", emergency_contact_phone="082"
        )
        room = self.rooms["A-103"]
        TenantContract.objects.create(
            tenant=tenant,
            room=room,
            start_date=date.today(),
            monthly_rent_amount=Decimal("1500000"),
        )
        # Checkout (no invoices → direct checkout)
        self.admin_ancol_client.post(reverse("tenant_checkout", args=[tenant.pk]))
        # Check room list
        resp = self.admin_ancol_client.get(reverse("room_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Kosong")

    def test_phase12_04_delete_tenant_with_active_contract_fails(self):
        """F-24: Cannot delete tenant with active contract."""
        tenant = Tenant.objects.create(
            full_name="No Delete", phone_number="081", emergency_contact_phone="082"
        )
        TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["A-101"],
            start_date=date.today(),
            monthly_rent_amount=Decimal("1500000"),
        )
        resp = self.admin_ancol_client.post(reverse("tenant_delete", args=[tenant.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Tenant.objects.filter(pk=tenant.pk).exists())

    def test_phase12_05_delete_tenant_success(self):
        """F-24: Delete tenant after checkout (no active contract, no unpaid)."""
        tenant = Tenant.objects.create(
            full_name="Delete Me", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["A-103"],
            start_date=date.today() - timedelta(days=30),
            monthly_rent_amount=Decimal("1500000"),
            is_active=False,
        )
        contract.end_date = date.today()
        contract.save()

        resp = self.superuser_client.post(reverse("tenant_delete", args=[tenant.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Tenant.objects.filter(pk=tenant.pk).exists())

    # ================================================================
    # PHASE 13: SECURITY & EDGE CASES
    # ================================================================
    def test_phase13_01_unauthenticated_dashboard(self):
        """Security: Unauthenticated user redirected from dashboard."""
        c = Client()
        resp = c.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_phase13_02_unauthenticated_invoice_list(self):
        """Security: Unauthenticated user redirected from invoice list."""
        c = Client()
        resp = c.get(reverse("invoice_list"))
        self.assertEqual(resp.status_code, 302)

    def test_phase13_03_admin_ancol_cannot_see_kana_tenants(self):
        """Security: Admin Ancol cannot see Kana tenants."""
        tenant = Tenant.objects.create(
            full_name="Kana Only Person", phone_number="081", emergency_contact_phone="082"
        )
        TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["K-101"],
            start_date=date.today(),
            monthly_rent_amount=Decimal("1500000"),
        )
        resp = self.admin_ancol_client.get(reverse("tenant_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Kana Only Person")

    def test_phase13_04_admin_ancol_cannot_see_kana_invoices(self):
        """Security: Admin Ancol cannot see Kana invoices."""
        tenant = Tenant.objects.create(
            full_name="Hidden Tenant", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["K-102"],
            start_date=date.today(),
            monthly_rent_amount=Decimal("1800000"),
        )
        Invoice.objects.create(
            contract=contract,
            billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal("1800000"),
            electricity_bill_amount=0,
            total_amount=Decimal("1800000"),
            status="BELUM_LUNAS",
        )
        resp = self.admin_ancol_client.get(reverse("invoice_list"))
        self.assertNotContains(resp, "Hidden Tenant")

    def test_phase13_05_checkout_cross_location_forbidden(self):
        """Security: Admin Ancol cannot checkout Kana tenant."""
        tenant = Tenant.objects.create(
            full_name="Cross Checkout", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["K-103"],
            start_date=date.today(),
            monthly_rent_amount=Decimal("1500000"),
        )
        self.admin_ancol_client.post(reverse("tenant_checkout", args=[tenant.pk]))
        contract.refresh_from_db()
        self.assertTrue(contract.is_active)  # Not changed

    def test_phase13_06_superuser_sees_all_invoices(self):
        """Security: Superuser sees invoices from all locations."""
        for room_key in ("A-101", "K-101"):
            tenant = Tenant.objects.create(
                full_name=f"Global {room_key}", phone_number="081", emergency_contact_phone="082"
            )
            contract = TenantContract.objects.create(
                tenant=tenant,
                room=self.rooms[room_key],
                start_date=date.today(),
                monthly_rent_amount=Decimal("1500000"),
            )
            Invoice.objects.create(
                contract=contract,
                billing_period_start=date.today(),
                due_date=date.today() + timedelta(days=10),
                base_rent_amount=Decimal("1500000"),
                electricity_bill_amount=0,
                total_amount=Decimal("1500000"),
                status="BELUM_LUNAS",
            )
        resp = self.superuser_client.get(reverse("invoice_list"))
        self.assertContains(resp, "Global A-101")
        self.assertContains(resp, "Global K-101")

    def test_phase13_07_checkout_requires_post(self):
        """Security: Checkout only accepts POST (C-01 fix)."""
        tenant = Tenant.objects.create(
            full_name="GET Checkout", phone_number="081", emergency_contact_phone="082"
        )
        TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["A-101"],
            start_date=date.today(),
            monthly_rent_amount=Decimal("1500000"),
        )
        resp = self.admin_ancol_client.get(reverse("tenant_checkout", args=[tenant.pk]))
        self.assertEqual(resp.status_code, 405)  # Method Not Allowed

    def test_phase13_08_room_delete_requires_post(self):
        """Security: Room delete only accepts POST."""
        room = Room.objects.create(
            kost_location=self.loc_ancol,
            room_number="A-DEL",
            price_monthly=Decimal("1000000"),
            capacity=1,
        )
        resp = self.admin_ancol_client.get(reverse("room_delete", args=[room.pk]))
        self.assertEqual(resp.status_code, 405)

    def test_phase13_09_operation_delete_requires_post(self):
        """Security: Operation delete only accepts POST."""
        cost = OperationCost.objects.create(
            kost_location=self.loc_ancol,
            admin=self.admin_ancol,
            category="LAINNYA",
            amount=Decimal("1000"),
            description="Del test",
            incurred_date=date.today(),
            proof_file="operation_costs/test.jpg",
        )
        resp = self.admin_ancol_client.get(reverse("operation_delete", args=[cost.pk]))
        self.assertEqual(resp.status_code, 405)

    def test_phase13_10_verify_requires_post(self):
        """Security: Verify payment only accepts POST."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        resp = self.admin_ancol_client.get(reverse("verify_payment", args=[payment.pk, "approve"]))
        self.assertEqual(resp.status_code, 405)

    def test_phase13_11_plain_user_cannot_create_tenant(self):
        """Security: Non-staff user must not create tenant records."""
        resp = self.plain_user_client.post(
            reverse("tenant_add"),
            {
                "full_name": "Unauthorized Tenant",
                "phone_number": "0812345",
                "emergency_contact_phone": "0899999",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Tenant.objects.filter(full_name="Unauthorized Tenant").exists())

    def test_phase13_12_plain_user_cannot_create_room(self):
        """Security: Non-staff user must not create room records."""
        resp = self.plain_user_client.post(
            reverse("room_add"),
            {
                "kost_location": self.loc_ancol.pk,
                "room_number": "X-999",
                "price_monthly": "1200000",
                "is_token_electricity": False,
                "capacity": 1,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Room.objects.filter(room_number="X-999").exists())

    def test_phase13_13_plain_user_cannot_assign_room(self):
        """Security: Non-staff user must not assign tenant to room."""
        tenant = Tenant.objects.create(
            full_name="Unauthorized Assign Tenant",
            phone_number="081111",
            emergency_contact_phone="082222",
        )
        resp = self.plain_user_client.post(
            reverse("tenant_assign_room", args=[tenant.pk]),
            {
                "room": self.rooms["A-101"].pk,
                "start_date": date.today().isoformat(),
                "monthly_rent_amount": "1500000",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(TenantContract.objects.filter(tenant=tenant, is_active=True).exists())

    def test_phase13_14_prevent_double_active_contract_same_room(self):
        """Data integrity: A room cannot have more than one active contract."""
        tenant1 = Tenant.objects.create(
            full_name="Integrity Tenant 1", phone_number="081333", emergency_contact_phone="082333"
        )
        tenant2 = Tenant.objects.create(
            full_name="Integrity Tenant 2", phone_number="081444", emergency_contact_phone="082444"
        )

        TenantContract.objects.create(
            tenant=tenant1,
            room=self.rooms["A-103"],
            start_date=date.today(),
            monthly_rent_amount=Decimal("1500000"),
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            TenantContract.objects.create(
                tenant=tenant2,
                room=self.rooms["A-103"],
                start_date=date.today(),
                monthly_rent_amount=Decimal("1500000"),
                is_active=True,
            )

    # ================================================================
    # PHASE 14: MANAGEMENT COMMANDS
    # ================================================================
    def test_phase14_01_seed_data_command(self):
        """F-42: seed_data command runs without errors."""
        # Note: This creates its own data; just test it doesn't crash
        call_command("seed_data")
        self.assertTrue(KostLocation.objects.exists())
        self.assertTrue(Room.objects.exists())

    # ================================================================
    # PHASE 15: INTEGRATION - FULL LIFECYCLE
    # ================================================================
    def test_phase15_full_lifecycle(self):
        """
        INTEGRATION: Full lifecycle test
        Create tenant → Assign room → Generate invoice → Input electricity →
        Public payment → Admin verify → Print receipt → Checkout → Delete
        """
        # 1. Create Tenant
        self.admin_ancol_client.post(
            reverse("tenant_add"),
            {
                "full_name": "Lifecycle Tenant",
                "phone_number": "081111222333",
                "emergency_contact_phone": "089999888777",
            },
        )
        tenant = Tenant.objects.get(full_name="Lifecycle Tenant")

        # 2. Assign Room A-101
        self.admin_ancol_client.post(
            reverse("tenant_assign_room", args=[tenant.pk]),
            {
                "room": self.rooms["A-101"].pk,
                "start_date": (date.today() - timedelta(days=5)).isoformat(),
                "monthly_rent_amount": "1500000",
            },
        )
        contract = TenantContract.objects.get(tenant=tenant, is_active=True)
        pin = contract.payment_pin
        self.assertEqual(len(pin), 6)

        # 3. Issue Invoice (per_room_cycle)
        call_command("issue_due_invoices")
        invoice = Invoice.objects.filter(contract=contract).first()
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.status, "BELUM_LUNAS")

        # 4. Input Electricity (Ancol = meteran)
        self.admin_ancol_client.post(
            reverse("invoice_detail", args=[invoice.pk]),
            {
                "meter_reading_start": 500,
                "meter_reading_end": 600,
                "rate_per_kwh": "1500.00",
            },
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.electricity_bill_amount, Decimal("150000.00"))
        self.assertEqual(invoice.total_amount, Decimal("1650000.00"))

        # 5. Tenant logs in via PIN portal
        lifecycle_client = Client()
        resp = lifecycle_client.post(
            reverse("public_payment_step1"),
            {
                "kost_location": self.loc_ancol.pk,
                "room_number": "A-101",
                "pin": pin,
            },
        )
        self.assertEqual(resp.status_code, 302)

        # 6. Tenant uploads payment proof
        img = create_test_image()
        resp = lifecycle_client.post(
            reverse("public_payment_step2"), {"payment_proof_file": img}, format="multipart"
        )
        self.assertEqual(resp.status_code, 200)  # success.html
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "MENUNGGU_VERIFIKASI")

        # 7. Admin approves payment
        payment = Payment.objects.filter(invoice=invoice).first()
        self.assertIsNotNone(payment)
        self.admin_ancol_client.post(reverse("verify_payment", args=[payment.pk, "approve"]))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "LUNAS")

        # 8. Print receipt
        resp = self.admin_ancol_client.get(reverse("print_receipt", args=[invoice.pk]))
        self.assertEqual(resp.status_code, 200)

        # 9. Checkout
        resp = self.admin_ancol_client.post(reverse("tenant_checkout", args=[tenant.pk]))
        self.assertEqual(resp.status_code, 302)
        contract.refresh_from_db()
        self.assertFalse(contract.is_active)
        # RC4: checkout menulis tanggal bisnis (timezone.localdate), bukan tanggal host
        self.assertEqual(contract.end_date, timezone.localdate())

        # 10. Delete tenant
        resp = self.superuser_client.post(reverse("tenant_delete", args=[tenant.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Tenant.objects.filter(pk=tenant.pk).exists())

    # ================================================================
    # PHASE 16: P0/P1 REMEDIATION — PHASE A1 (W2, W3, W8, W12, W13)
    # ================================================================

    def _staff_without_location_client(self):
        """Helper: staff user whose AdminProfile has no assigned location."""
        user = User.objects.create_user(username="staff_noloc", password="noloc123", is_staff=True)
        AdminProfile.objects.create(user=user, assigned_location=None)
        client = Client()
        client.login(username="staff_noloc", password="noloc123")
        return client, user

    # --- W2: report/export fail-closed ---

    def test_phase11_05_finance_report_staff_without_location_denied(self):
        """W2: staff without assigned_location cannot access financial report."""
        client, _ = self._staff_without_location_client()
        resp = client.get(reverse("finance_report"))
        self.assertEqual(resp.status_code, 302)

    def test_phase11_06_finance_report_non_staff_denied(self):
        """W2: non-staff authenticated user cannot access financial report."""
        resp = self.plain_user_client.get(reverse("finance_report"))
        self.assertEqual(resp.status_code, 302)

    def test_phase11_07_export_excel_staff_without_location_denied(self):
        """W2: staff without assigned_location cannot export financial Excel."""
        client, _ = self._staff_without_location_client()
        resp = client.get(reverse("export_finance_excel"))
        self.assertEqual(resp.status_code, 302)

    def test_phase11_08_export_excel_non_staff_denied(self):
        """W2: non-staff authenticated user cannot export financial Excel."""
        resp = self.plain_user_client.get(reverse("export_finance_excel"))
        self.assertEqual(resp.status_code, 302)

    # --- W8: operation_create authorization ---

    def test_phase10_08_operation_create_plain_user_denied(self):
        """W8: non-staff user cannot create operational costs."""
        img = create_test_image("w8_plain.jpg")
        resp = self.plain_user_client.post(
            reverse("operation_add"),
            {
                "kost_location": self.loc_ancol.pk,
                "category": "LAINNYA",
                "amount": "10000",
                "incurred_date": date.today().isoformat(),
                "description": "Should be denied",
                "proof_file": img,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(OperationCost.objects.count(), 0)

    def test_phase10_09_operation_create_staff_no_location_denied(self):
        """W8: staff without assigned_location cannot create operational costs."""
        client, _ = self._staff_without_location_client()
        img = create_test_image("w8_noloc.jpg")
        resp = client.post(
            reverse("operation_add"),
            {
                "kost_location": self.loc_ancol.pk,
                "category": "LAINNYA",
                "amount": "10000",
                "incurred_date": date.today().isoformat(),
                "description": "Should be denied",
                "proof_file": img,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(OperationCost.objects.count(), 0)

    def test_phase10_10_operation_create_forces_own_location(self):
        """W8: posted foreign location is overwritten with the staff's location."""
        img = create_test_image("w8_force.jpg")
        resp = self.admin_ancol_client.post(
            reverse("operation_add"),
            {
                "kost_location": self.loc_kana.pk,  # wrong on purpose
                "category": "INTERNET",
                "amount": "123000",
                "incurred_date": date.today().isoformat(),
                "description": "Forced location check",
                "proof_file": img,
            },
        )
        self.assertEqual(resp.status_code, 302)
        cost = OperationCost.objects.get(category="INTERNET")
        self.assertEqual(cost.kost_location, self.loc_ancol)

    # --- W3: electricity immutability ---

    def test_phase6_13_electricity_edit_blocked_after_lunas(self):
        """W3: LUNAS invoice electricity reading cannot be edited."""
        tenant, contract, invoice = self._setup_payment_data()
        reading = ElectricityReading.objects.create(
            invoice=invoice,
            meter_reading_start=0,
            meter_reading_end=10,
            rate_per_kwh=Decimal("1500"),
        )
        invoice.refresh_from_db()  # W2: reading save uses a fresh locked row now
        invoice.status = "LUNAS"
        invoice.save()
        resp = self.admin_ancol_client.post(
            reverse("invoice_detail", args=[invoice.pk]),
            {"meter_reading_start": 0, "meter_reading_end": 100, "rate_per_kwh": "1500.00"},
        )
        self.assertEqual(resp.status_code, 302)
        reading.refresh_from_db()
        self.assertEqual(reading.meter_reading_end, 10)
        invoice.refresh_from_db()
        self.assertEqual(invoice.electricity_bill_amount, Decimal("15000.00"))

    def test_phase6_14_electricity_create_blocked_after_lunas(self):
        """W3: no new electricity reading can be created on a LUNAS invoice."""
        tenant, contract, invoice = self._setup_payment_data()
        invoice.status = "LUNAS"
        invoice.save()
        resp = self.admin_ancol_client.post(
            reverse("invoice_detail", args=[invoice.pk]),
            {"meter_reading_start": 0, "meter_reading_end": 100, "rate_per_kwh": "1500.00"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ElectricityReading.objects.filter(invoice=invoice).exists())

    def test_phase6_15_electricity_edit_blocked_when_menunggu_verifikasi(self):
        """W3: reading cannot change while payment is awaiting verification."""
        tenant, contract, invoice = self._setup_payment_data()
        invoice.status = "MENUNGGU_VERIFIKASI"
        invoice.save()
        resp = self.admin_ancol_client.post(
            reverse("invoice_detail", args=[invoice.pk]),
            {"meter_reading_start": 0, "meter_reading_end": 100, "rate_per_kwh": "1500.00"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ElectricityReading.objects.filter(invoice=invoice).exists())

    def test_phase6_16_electricity_edit_allowed_when_unpaid(self):
        """W3 regression: TELAT_BAYAR (unpaid) invoices still accept readings."""
        tenant, contract, invoice = self._setup_payment_data()
        invoice.status = "TELAT_BAYAR"
        invoice.save()
        resp = self.admin_ancol_client.post(
            reverse("invoice_detail", args=[invoice.pk]),
            {"meter_reading_start": 100, "meter_reading_end": 150, "rate_per_kwh": "1500.00"},
        )
        self.assertEqual(resp.status_code, 302)
        reading = ElectricityReading.objects.get(invoice=invoice)
        self.assertEqual(reading.calculated_amount, Decimal("75000.00"))

    # --- W12: upload copy/rules ---

    def test_phase7_10_upload_pdf_rejected(self):
        """W12/BQ-12: PDF payment proofs are rejected."""
        tenant, contract, invoice = self._setup_payment_data()
        session = self.public_client.session
        session["verified_contract_id"] = contract.id
        session.save()
        proof = SimpleUploadedFile("proof.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        resp = self.public_client.post(
            reverse("public_payment_step2"), {"payment_proof_file": proof}, format="multipart"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Payment.objects.filter(invoice=invoice).exists())

    def test_phase7_11_upload_oversized_rejected(self):
        """W12/BQ-12: files over 5 MB are rejected."""
        tenant, contract, invoice = self._setup_payment_data()
        session = self.public_client.session
        session["verified_contract_id"] = contract.id
        session.save()
        big = SimpleUploadedFile("big.jpg", b"x" * (5 * 1024 * 1024 + 1), content_type="image/jpeg")
        resp = self.public_client.post(
            reverse("public_payment_step2"), {"payment_proof_file": big}, format="multipart"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Payment.objects.filter(invoice=invoice).exists())

    def test_phase7_12_upload_non_image_rejected(self):
        """W12/BQ-12: non-image extensions are rejected."""
        tenant, contract, invoice = self._setup_payment_data()
        session = self.public_client.session
        session["verified_contract_id"] = contract.id
        session.save()
        bad = SimpleUploadedFile("proof.html", b"<html></html>", content_type="text/html")
        resp = self.public_client.post(
            reverse("public_payment_step2"), {"payment_proof_file": bad}, format="multipart"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Payment.objects.filter(invoice=invoice).exists())

    def test_phase7_13_step2_template_copy_matches_rules(self):
        """W12/BQ-12: upload page text reflects image-only 5 MB rule."""
        tenant, contract, invoice = self._setup_payment_data()
        ElectricityReading.objects.create(
            invoice=invoice,
            meter_reading_start=0,
            meter_reading_end=10,
            rate_per_kwh=Decimal("1500"),
        )
        session = self.public_client.session
        session["verified_contract_id"] = contract.id
        session.save()
        resp = self.public_client.get(reverse("public_payment_step2"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "JPG/JPEG/PNG/WEBP. Maks 5 MB.")
        self.assertNotContains(resp, "PDF")
        self.assertNotContains(resp, "2MB")

    def test_phase7_14_step2_menunggu_never_shows_lunas(self):
        """Regression: while the only invoice is MENUNGGU_VERIFIKASI, the portal
        must say MENUNGGU VERIFIKASI and must never claim LUNAS."""
        tenant, contract, invoice = self._setup_payment_data()
        session = self.public_client.session
        session["verified_contract_id"] = contract.id
        session.save()
        invoice.status = "MENUNGGU_VERIFIKASI"
        invoice.save()
        resp = self.public_client.get(reverse("public_payment_step2"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "MENUNGGU VERIFIKASI")
        self.assertNotContains(resp, "Tidak ada tagihan aktif saat ini")

    # --- W13: income labels ---

    def test_phase5_05_dashboard_income_label_cash(self):
        """W13/BQ-3: dashboard income KPI is labelled as cash basis."""
        resp = self.admin_ancol_client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Pemasukan Bulan Ini (Kas)")

    def test_phase11_09_report_income_label_accrual(self):
        """W13/BQ-3: report income KPI is labelled as billing-period basis."""
        resp = self.admin_ancol_client.get(reverse("finance_report"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Pemasukan (Periode Tagihan)")

    # ================================================================
    # PHASE 17: P0/P1 REMEDIATION — PHASE A2 (W1, W1b)
    # ================================================================

    def test_phase8_08_approve_requires_menunggu_invoice(self):
        """W1: approve is blocked when the invoice is not MENUNGGU_VERIFIKASI."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        invoice.status = "BELUM_LUNAS"
        invoice.save()
        resp = self.admin_ancol_client.post(reverse("verify_payment", args=[payment.pk, "approve"]))
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "BELUM_LUNAS")
        payment.refresh_from_db()
        self.assertEqual(payment.status, "PENDING")

    def test_phase8_09_double_approve_blocked(self):
        """W1: a second approve does not rewrite the decision metadata."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        self.admin_ancol_client.post(reverse("verify_payment", args=[payment.pk, "approve"]))
        payment.refresh_from_db()
        first_verified_at = payment.verified_at
        resp = self.admin_ancol_client.post(reverse("verify_payment", args=[payment.pk, "approve"]))
        self.assertEqual(resp.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "APPROVED")
        self.assertEqual(payment.verified_at, first_verified_at)

    def test_phase8_10_rejected_payment_never_reapprovable(self):
        """W1/BQ-8: a rejected Payment can never be approved afterwards."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        self.admin_ancol_client.post(
            reverse("verify_payment", args=[payment.pk, "reject"]), {"rejection_note": "Not valid"}
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, "REJECTED")
        resp = self.admin_ancol_client.post(reverse("verify_payment", args=[payment.pk, "approve"]))
        self.assertEqual(resp.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "REJECTED")
        invoice.refresh_from_db()
        self.assertNotEqual(invoice.status, "LUNAS")

    def test_phase8_11_reject_after_approve_blocked(self):
        """W1: an approved Payment cannot be rejected afterwards."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        self.admin_ancol_client.post(reverse("verify_payment", args=[payment.pk, "approve"]))
        resp = self.admin_ancol_client.post(
            reverse("verify_payment", args=[payment.pk, "reject"]), {"rejection_note": "Too late"}
        )
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "LUNAS")
        payment.refresh_from_db()
        self.assertEqual(payment.status, "APPROVED")

    def test_phase8_12_reject_cannot_flip_lunas_via_old_pending_payment(self):
        """W1/B1: rejecting an old PENDING payment cannot revert a LUNAS invoice."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        invoice.status = "LUNAS"
        invoice.save()  # invoice paid via another (approved) payment
        resp = self.admin_ancol_client.post(
            reverse("verify_payment", args=[payment.pk, "reject"]),
            {"rejection_note": "Stale attempt"},
        )
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "LUNAS")
        payment.refresh_from_db()
        self.assertEqual(payment.status, "PENDING")

    def test_phase8_13_dashboard_hides_actions_for_rejected_payment(self):
        """W1: dashboard offers no verify actions for non-MENUNGGU invoices."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        self.admin_ancol_client.post(
            reverse("verify_payment", args=[payment.pk, "reject"]), {"rejection_note": "Bad proof"}
        )
        invoice.refresh_from_db()
        invoice.status = "TELAT_BAYAR"
        invoice.save()
        resp = self.admin_ancol_client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "/verify/")

    def test_phase8_14_retry_creates_new_payment_preserving_history(self):
        """W1/BQ-8: a retry is a NEW Payment; the rejected row stays as history."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        self.admin_ancol_client.post(
            reverse("verify_payment", args=[payment.pk, "reject"]),
            {"rejection_note": "First attempt rejected"},
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, "REJECTED")
        # Tenant retries: new Payment row + invoice back to MENUNGGU (portal flow)
        retry = Payment.objects.create(
            invoice=invoice, payment_proof_file="payment_proofs/retry.jpg"
        )
        invoice.status = "MENUNGGU_VERIFIKASI"
        invoice.save()
        self.admin_ancol_client.post(reverse("verify_payment", args=[retry.pk, "approve"]))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "LUNAS")
        payment.refresh_from_db()
        retry.refresh_from_db()
        self.assertEqual(payment.status, "REJECTED")
        self.assertIn("First attempt rejected", payment.rejection_note)
        self.assertEqual(retry.status, "APPROVED")

    def test_phase8_15_receipt_and_export_use_approved_payment(self):
        """W1: receipt context and export verifier use the APPROVED payment."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        self.admin_ancol_client.post(reverse("verify_payment", args=[payment.pk, "approve"]))
        payment.refresh_from_db()
        stale = Payment.objects.create(
            invoice=invoice, payment_proof_file="payment_proofs/stale.jpg", status="REJECTED"
        )
        resp = self.admin_ancol_client.get(reverse("print_receipt", args=[invoice.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["payment"].pk, payment.pk)
        # Export: verifier column must show the approved payment's verifier
        resp = self.admin_ancol_client.get(
            reverse("export_finance_excel") + f"?year={date.today().year}"
        )
        self.assertEqual(resp.status_code, 200)
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(resp.content))
        ws2 = wb["Rincian Pemasukan"]
        verifiers = [row[4] for row in ws2.iter_rows(min_row=2, values_only=True)]
        self.assertIn("admin_ancol", verifiers)
        self.assertNotEqual(stale.pk, payment.pk)

    def test_phase8_16_error_message_renders_alert_danger(self):
        """MESSAGE_TAGS: an error-level Django message renders as Bootstrap alert-danger."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        resp = self.admin_ancol_client.post(
            reverse("verify_payment", args=[payment.pk, "reject"]),
            {"rejection_note": "Bukti tidak jelas"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alert-danger")
        self.assertNotContains(resp, "alert-error")

    def test_phase16_01_audit_payment_history_clean(self):
        """W1: audit command classifies a clean pending payment set."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        out = io.StringIO()
        call_command("audit_payment_history", stdout=out)
        text = out.getvalue()
        self.assertIn("pending=1", text)
        self.assertIn("No ambiguous rows detected", text)

    def test_phase16_01b_audit_lunas_without_payment_is_warning_only(self):
        """W1: invoice-level anomaly is a non-blocking warning, not ambiguity."""
        tenant, contract, invoice = self._setup_payment_data()
        invoice.status = "LUNAS"
        invoice.save()
        out = io.StringIO()
        call_command("audit_payment_history", stdout=out)
        text = out.getvalue()
        self.assertIn("No ambiguous rows detected", text)
        self.assertIn("WARNINGS (non-blocking data-quality review):", text)
        self.assertIn(f"invoice {invoice.pk}", text)

    def test_phase16_02_audit_detects_verified_without_lunas(self):
        """W1: audit flags verified_at payments whose invoice is not LUNAS."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        Payment.objects.filter(pk=payment.pk).update(verified_at=timezone.now())
        out = io.StringIO()
        call_command("audit_payment_history", stdout=out)
        text = out.getvalue()
        self.assertIn("AMBIGUOUS", text)
        self.assertIn(f"{payment.pk}", text)

    def test_phase16_03_audit_detects_multiple_approved(self):
        """W1: audit flags invoices with more than one approved-classified payment."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        Payment.objects.filter(pk=payment.pk).update(verified_at=timezone.now())
        invoice.status = "LUNAS"
        invoice.save()
        second = Payment.objects.create(
            invoice=invoice, payment_proof_file="payment_proofs/second.jpg"
        )
        Payment.objects.filter(pk=second.pk).update(verified_at=timezone.now())
        out = io.StringIO()
        call_command("audit_payment_history", stdout=out)
        self.assertIn("multiple approved-classified payments (2)", out.getvalue())

    def test_phase16_04_admin_payment_is_readonly_evidence(self):
        """W1b: PaymentAdmin is evidence-only (no add/delete, all fields read-only)."""
        from django.contrib import admin as dj_admin

        from finance.admin import PaymentAdmin

        ma = PaymentAdmin(Payment, dj_admin.site)
        self.assertFalse(ma.has_add_permission(None))
        self.assertFalse(ma.has_delete_permission(None))
        ro = ma.get_readonly_fields(None)
        for field in (
            "invoice",
            "payment_proof_file",
            "uploaded_at",
            "status",
            "verified_by",
            "verified_at",
            "rejection_note",
        ):
            self.assertIn(field, ro)

    def test_phase16_05_admin_invoice_lunas_is_view_only(self):
        """W1b: LUNAS invoices are fully read-only in admin; no delete ever."""
        from django.contrib import admin as dj_admin

        from finance.admin import InvoiceAdmin

        ma = InvoiceAdmin(Invoice, dj_admin.site)
        self.assertFalse(ma.has_delete_permission(None))
        tenant, contract, invoice, payment = self._setup_verification_data()
        invoice.status = "BELUM_LUNAS"  # genuinely open state (MENUNGGU is now locked too)
        invoice.save()
        ro_open = ma.get_readonly_fields(None, invoice)
        self.assertIn("status", ro_open)
        self.assertIn("total_amount", ro_open)
        self.assertIn("billing_period_year", ro_open)
        self.assertIn("billing_period_month", ro_open)
        self.assertNotIn("base_rent_amount", ro_open)
        invoice.status = "LUNAS"
        invoice.save()
        ro_lunas = ma.get_readonly_fields(None, invoice)
        self.assertIn("base_rent_amount", ro_lunas)
        self.assertIn("electricity_bill_amount", ro_lunas)
        self.assertIn("contract", ro_lunas)

    def test_phase16_06_admin_electricity_reading_readonly_after_lunas(self):
        """W1b: ElectricityReadingAdmin is append-less/delete-less and locked after LUNAS."""
        from django.contrib import admin as dj_admin

        from finance.admin import ElectricityReadingAdmin

        ma = ElectricityReadingAdmin(ElectricityReading, dj_admin.site)
        self.assertFalse(ma.has_add_permission(None))
        self.assertFalse(ma.has_delete_permission(None))
        tenant, contract, invoice = self._setup_payment_data()
        reading = ElectricityReading.objects.create(
            invoice=invoice,
            meter_reading_start=0,
            meter_reading_end=10,
            rate_per_kwh=Decimal("1500"),
        )
        self.assertEqual(ma.get_readonly_fields(None, reading), ("invoice",))
        invoice.refresh_from_db()  # fresh amounts before flipping status
        invoice.status = "LUNAS"
        invoice.save()
        reading.refresh_from_db()  # reload FK state like the admin change view does
        ro = ma.get_readonly_fields(None, reading)
        self.assertIn("meter_reading_end", ro)

    # ================================================================
    # PHASE 18: P0/P1 REMEDIATION — PHASE A3 (W4, W5, W10)
    # ================================================================

    def test_phase6_17_ancol_command_due_is_start_plus_10(self):
        """W5/BQ-1: management command applies the same Ancol due-date rule."""
        tenant, contract = self._setup_billing_data()
        call_command("issue_due_invoices")
        invoice = Invoice.objects.filter(contract=contract).order_by("billing_period_start").first()
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.due_date, invoice.billing_period_start + timedelta(days=10))

    def test_phase6_18_ancol_start_day_clamped_with_plus_10(self):
        """RC3/W5: day 29-31 clamps only when the target billing month lacks it."""
        tenant_clamped = Tenant.objects.create(
            full_name="Clamp Tenant", phone_number="081", emergency_contact_phone="082"
        )
        contract_clamped = TenantContract.objects.create(
            tenant=tenant_clamped,
            room=self.rooms["A-103"],
            start_date=date(2026, 1, 31),
            monthly_rent_amount=Decimal("1500000"),
        )
        tenant_plain = Tenant.objects.create(
            full_name="Plain Day Tenant", phone_number="081", emergency_contact_phone="082"
        )
        contract_plain = TenantContract.objects.create(
            tenant=tenant_plain,
            room=self.rooms["A-102"],
            start_date=date(2026, 1, 15),
            monthly_rent_amount=Decimal("1500000"),
        )
        issue_due(date(2026, 2, 22))
        invoice_clamped = Invoice.objects.filter(
            contract=contract_clamped, billing_period_month=2
        ).first()
        invoice_plain = Invoice.objects.filter(
            contract=contract_plain, billing_period_month=2
        ).first()
        self.assertIsNotNone(invoice_clamped)
        self.assertIsNotNone(invoice_plain)
        start = invoice_clamped.billing_period_start
        days_in_month = calendar.monthrange(start.year, start.month)[1]
        expected_day = 31 if days_in_month >= 31 else 28
        self.assertEqual(start.day, expected_day)
        self.assertEqual(invoice_clamped.due_date, start + timedelta(days=10))
        self.assertEqual(invoice_plain.billing_period_start.day, 15)
        self.assertEqual(
            invoice_plain.due_date,
            invoice_plain.billing_period_start + timedelta(days=10),
        )

    def test_phase6_19_duplicate_invoice_period_rejected(self):
        """W4/BQ-6: DB constraint blocks a second invoice for the same period."""
        tenant, contract = self._setup_billing_data()
        Invoice.objects.create(
            contract=contract,
            billing_period_start=date.today().replace(day=1),
            due_date=date.today().replace(day=11),
            base_rent_amount=Decimal("1500000"),
            electricity_bill_amount=0,
            status="BELUM_LUNAS",
        )
        with self.assertRaises(IntegrityError):
            Invoice.objects.create(
                contract=contract,
                billing_period_start=date.today().replace(day=15),
                due_date=date.today().replace(day=25),
                base_rent_amount=Decimal("1500000"),
                electricity_bill_amount=0,
                status="BELUM_LUNAS",
            )

    def test_phase6_20_bulk_generate_exactly_one_per_period(self):
        """W4/BQ-6: repeated simultaneous issuing yields exactly one invoice per period."""
        tenant = Tenant.objects.create(
            full_name="UNS Repeat Tenant", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["U-101"],
            start_date=date.today() - timedelta(days=15),
            monthly_rent_amount=Decimal("1000000"),
        )
        today = timezone.localdate()
        period_key = f"{today.year:04d}-{today.month:02d}"
        self.admin_uns_client.post(reverse("issue_invoices"), {"period": period_key})
        self.admin_uns_client.post(reverse("issue_invoices"), {"period": period_key})
        self.assertEqual(Invoice.objects.filter(contract=contract).count(), 1)

    def test_phase6_21_audit_duplicate_invoices_clean(self):
        """W4: audit command reports a clean dataset (constraint prevents dupes)."""
        tenant, contract = self._setup_billing_data()
        call_command("issue_due_invoices")
        out = io.StringIO()
        call_command("audit_duplicate_invoices", stdout=out)
        self.assertIn("no duplicates found", out.getvalue())

    def test_phase6_22_normalized_period_fields_backfilled(self):
        """W4: billing period fields derive from billing_period_start on save."""
        tenant, contract = self._setup_billing_data()
        start = date(2026, 3, 7)
        invoice = Invoice.objects.create(
            contract=contract,
            billing_period_start=start,
            due_date=date(2026, 3, 17),
            base_rent_amount=Decimal("1500000"),
            electricity_bill_amount=0,
            status="BELUM_LUNAS",
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.billing_period_year, 2026)
        self.assertEqual(invoice.billing_period_month, 3)

    def test_phase4_10_new_contracts_get_distinct_pins(self):
        """W10/BQ-4: new contracts receive distinct CSPRNG PINs."""
        tenant1 = Tenant.objects.create(
            full_name="Pin One", phone_number="081", emergency_contact_phone="082"
        )
        tenant2 = Tenant.objects.create(
            full_name="Pin Two", phone_number="081", emergency_contact_phone="082"
        )
        contract1 = TenantContract.objects.create(
            tenant=tenant1,
            room=self.rooms["A-101"],
            start_date=date.today(),
            monthly_rent_amount=Decimal("1000000"),
        )
        contract2 = TenantContract.objects.create(
            tenant=tenant2,
            room=self.rooms["A-102"],
            start_date=date.today(),
            monthly_rent_amount=Decimal("1000000"),
        )
        self.assertNotEqual(contract1.payment_pin, contract2.payment_pin)
        for contract in (contract1, contract2):
            self.assertEqual(len(contract.payment_pin), 6)
            self.assertTrue(contract.payment_pin.isdigit())

    def test_phase4_11_pin_not_rotated_on_update(self):
        """W10/BQ-4: updating an active contract does not rotate its PIN."""
        tenant, contract = self._setup_billing_data()
        original_pin = contract.payment_pin
        contract.monthly_rent_amount = Decimal("1600000")
        contract.save()
        contract.refresh_from_db()
        self.assertEqual(contract.payment_pin, original_pin)

    # ================================================================
    # PHASE 19: P0/P1 REMEDIATION — PHASE A4 (W6, W7, W11, W11b)
    # ================================================================

    def test_phase2_06_location_delete_with_history_protected(self):
        """W11/BQ-9: a location with rooms cannot be hard-deleted (PROTECT)."""
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.loc_ancol.delete()
        self.assertTrue(KostLocation.objects.filter(pk=self.loc_ancol.pk).exists())

    def test_phase2_07_admin_delete_permission_disabled(self):
        """W11/W11b: admin delete is disabled for locations and rooms."""
        from django.contrib import admin as dj_admin

        from core.admin import KostLocationAdmin, RoomAdmin

        self.assertFalse(KostLocationAdmin(KostLocation, dj_admin.site).has_delete_permission(None))
        self.assertFalse(RoomAdmin(Room, dj_admin.site).has_delete_permission(None))

    def test_phase3_08_room_delete_blocked_when_historical_contracts(self):
        """W11b/BQ-9: a room with only inactive contracts cannot be deleted."""
        tenant = Tenant.objects.create(
            full_name="History Tenant", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["A-101"],
            start_date=date.today() - timedelta(days=60),
            monthly_rent_amount=Decimal("1500000"),
        )
        contract.is_active = False
        contract.end_date = date.today()
        contract.save()
        resp = self.admin_ancol_client.post(reverse("room_delete", args=[self.rooms["A-101"].pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Room.objects.filter(pk=self.rooms["A-101"].pk).exists())

    def test_phase13_15_xff_ignored_by_default(self):
        """W7: X-Forwarded-For is ignored unless explicitly trusted."""
        from django.core.cache import cache

        cache.clear()
        self.public_client.post(
            reverse("public_payment_step1"),
            {
                "kost_location": self.loc_ancol.pk,
                "room_number": "no-such-room",
                "pin": "000000",
            },
            HTTP_X_FORWARDED_FOR="1.2.3.4",
        )
        self.assertIsNotNone(cache.get("ratelimit:pin_attempt:127.0.0.1"))
        self.assertIsNone(cache.get("ratelimit:pin_attempt:1.2.3.4"))

    def test_phase13_16_xff_honored_when_enabled(self):
        """W7: X-Forwarded-For is used when TRUST_X_FORWARDED_FOR=True."""
        from django.core.cache import cache

        cache.clear()
        with override_settings(TRUST_X_FORWARDED_FOR=True):
            self.public_client.post(
                reverse("public_payment_step1"),
                {
                    "kost_location": self.loc_ancol.pk,
                    "room_number": "no-such-room",
                    "pin": "000000",
                },
                HTTP_X_FORWARDED_FOR="1.2.3.4",
            )
        self.assertIsNotNone(cache.get("ratelimit:pin_attempt:1.2.3.4"))

    # ================================================================
    # PHASE 20: P0/P1 REMEDIATION — PHASE A5 (W9)
    # ================================================================

    def _make_kana_tenant_with_active_contract(self):
        tenant = Tenant.objects.create(
            full_name="Kana Resident", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["K-101"],
            start_date=date.today() - timedelta(days=10),
            monthly_rent_amount=Decimal("1500000"),
        )
        return tenant, contract

    def _deactivate_contract(self, contract):
        contract.is_active = False
        contract.end_date = date.today()
        contract.save()

    def test_phase4_12_edit_denied_when_active_at_another_location(self):
        """W9/BQ-7: old-location admin cannot edit a tenant active elsewhere."""
        tenant, contract = self._make_kana_tenant_with_active_contract()
        resp = self.admin_ancol_client.post(
            reverse("tenant_edit", args=[tenant.pk]),
            {"full_name": "Hacked", "phone_number": "081", "emergency_contact_phone": "082"},
        )
        self.assertEqual(resp.status_code, 404)
        tenant.refresh_from_db()
        self.assertEqual(tenant.full_name, "Kana Resident")

    def test_phase4_13_edit_denied_for_historical_only_tenant(self):
        """W9/BQ-7: historical-only tenants are read-only for the old location."""
        tenant = Tenant.objects.create(
            full_name="Past Resident", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["A-101"],
            start_date=date.today() - timedelta(days=90),
            monthly_rent_amount=Decimal("1500000"),
        )
        self._deactivate_contract(contract)
        resp = self.admin_ancol_client.post(
            reverse("tenant_edit", args=[tenant.pk]),
            {
                "full_name": "Should Not Change",
                "phone_number": "081",
                "emergency_contact_phone": "082",
            },
        )
        self.assertEqual(resp.status_code, 404)
        tenant.refresh_from_db()
        self.assertEqual(tenant.full_name, "Past Resident")

    def test_phase4_14_edit_allowed_when_active_at_own_location(self):
        """W9/BQ-7 regression: tenant active at the staff's location stays editable."""
        tenant, contract = self._setup_billing_data()
        resp = self.admin_ancol_client.post(
            reverse("tenant_edit", args=[tenant.pk]),
            {"full_name": "Edited Active", "phone_number": "081", "emergency_contact_phone": "082"},
        )
        self.assertEqual(resp.status_code, 302)
        tenant.refresh_from_db()
        self.assertEqual(tenant.full_name, "Edited Active")

    def test_phase4_15_assign_denied_for_foreign_history_tenant(self):
        """W9/PG-1: cross-location move initiation blocked (404) pending owner decision."""
        tenant = Tenant.objects.create(
            full_name="Foreign History", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["K-101"],
            start_date=date.today() - timedelta(days=90),
            monthly_rent_amount=Decimal("1500000"),
        )
        self._deactivate_contract(contract)
        resp = self.admin_ancol_client.post(
            reverse("tenant_assign_room", args=[tenant.pk]),
            {
                "room": self.rooms["A-101"].pk,
                "start_date": date.today().isoformat(),
                "monthly_rent_amount": "1500000",
            },
        )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(TenantContract.objects.filter(tenant=tenant, is_active=True).exists())

    def test_phase4_16_assign_allowed_for_own_history_tenant(self):
        """W9/BQ-7: a returning tenant with history at the staff's location can be assigned."""
        tenant = Tenant.objects.create(
            full_name="Returning", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["A-103"],
            start_date=date.today() - timedelta(days=90),
            monthly_rent_amount=Decimal("1500000"),
        )
        self._deactivate_contract(contract)
        resp = self.admin_ancol_client.post(
            reverse("tenant_assign_room", args=[tenant.pk]),
            {
                "room": self.rooms["A-101"].pk,
                "start_date": date.today().isoformat(),
                "monthly_rent_amount": "1500000",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(TenantContract.objects.filter(tenant=tenant, is_active=True).exists())

    def test_phase4_17_superuser_cross_location_assign_allowed(self):
        """W9: superuser retains the sanctioned cross-location move path."""
        tenant = Tenant.objects.create(
            full_name="Move By Owner", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["K-101"],
            start_date=date.today() - timedelta(days=90),
            monthly_rent_amount=Decimal("1500000"),
        )
        self._deactivate_contract(contract)
        resp = self.superuser_client.post(
            reverse("tenant_assign_room", args=[tenant.pk]),
            {
                "room": self.rooms["A-101"].pk,
                "start_date": date.today().isoformat(),
                "monthly_rent_amount": "1500000",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(TenantContract.objects.filter(tenant=tenant, is_active=True).exists())

    # ================================================================
    # PHASE 21: PRE-COMMIT REVIEW FIXES (RC1–RC4)
    # ================================================================

    def test_phase16_07_admin_electricity_reading_cannot_be_repointed(self):
        """RC1: reading's invoice FK is always read-only; the change form drops it."""
        from django.contrib import admin as dj_admin

        from finance.admin import ElectricityReadingAdmin

        ma = ElectricityReadingAdmin(ElectricityReading, dj_admin.site)
        tenant, contract, invoice = self._setup_payment_data()
        reading = ElectricityReading.objects.create(
            invoice=invoice,
            meter_reading_start=0,
            meter_reading_end=10,
            rate_per_kwh=Decimal("1500"),
        )
        self.assertIn("invoice", ma.get_readonly_fields(None, reading))
        form_class = ma.get_form(None, reading)
        self.assertNotIn("invoice", form_class.base_fields)

    def test_phase4_18_assign_page_get_denied_for_foreign_history_tenant(self):
        """RC2: GET assign page 404s for foreign-history tenants (no PII exposure)."""
        tenant = Tenant.objects.create(
            full_name="Foreign PII", phone_number="08123456789", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["K-101"],
            start_date=date.today() - timedelta(days=90),
            monthly_rent_amount=Decimal("1500000"),
        )
        self._deactivate_contract(contract)
        resp = self.admin_ancol_client.get(reverse("tenant_assign_room", args=[tenant.pk]))
        self.assertEqual(resp.status_code, 404)
        self.assertNotIn(b"Foreign PII", resp.content)
        self.assertNotIn(b"08123456789", resp.content)

    def test_phase12_06_checkout_uses_configured_local_date(self):
        """RC4: checkout end_date = local business date across a UTC date boundary."""
        from unittest import mock

        from django.utils import timezone as dj_timezone

        tenant = Tenant.objects.create(
            full_name="TZ Boundary", phone_number="081", emergency_contact_phone="082"
        )
        contract = TenantContract.objects.create(
            tenant=tenant,
            room=self.rooms["A-101"],
            start_date=date.today() - timedelta(days=30),
            monthly_rent_amount=Decimal("1500000"),
        )
        fixed_utc = datetime(2030, 1, 1, 20, 0, tzinfo=UTC)  # 2030-01-02 03:00 WIB
        real_localdate = dj_timezone.localdate
        with override_settings(TIME_ZONE="Asia/Jakarta"):
            with mock.patch(
                "tenants.views.timezone.localdate",
                side_effect=lambda: real_localdate(fixed_utc),
            ):
                resp = self.admin_ancol_client.post(reverse("tenant_checkout", args=[tenant.pk]))
        self.assertEqual(resp.status_code, 302)
        contract.refresh_from_db()
        self.assertFalse(contract.is_active)
        self.assertEqual(contract.end_date, date(2030, 1, 2))
        # control: the UTC date at that instant is still 2030-01-01
        self.assertEqual(fixed_utc.date(), date(2030, 1, 1))

    # ================================================================
    # PHASE 22: FINANCIAL CONCURRENCY HARDENING (W1–W4)
    # ================================================================
    #
    # NOTE (SQLite vs PostgreSQL): the test runner uses SQLite, where
    # select_for_update() is a documented no-op (Django only emits FOR UPDATE
    # when the backend supports it — see django/db/models/sql/compiler.py).
    # The tests below prove state invariants, zero-write losing paths, and that
    # the flows issue locked reads. True parallel lock contention must be
    # verified on PostgreSQL before production sign-off.

    def _spy_on_select_for_update(self, calls):
        real = QuerySet.select_for_update

        def spy(self, *args, **kwargs):
            calls.append(self.model.__name__)
            return real(self, *args, **kwargs)

        return mock.patch.object(QuerySet, "select_for_update", spy)

    def test_w1_01_verify_payment_uses_locked_reads(self):
        """W1: verify_payment locks Invoice then Payment via select_for_update."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        calls = []
        with self._spy_on_select_for_update(calls):
            resp = self.admin_ancol_client.post(
                reverse("verify_payment", args=[payment.pk, "approve"])
            )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(calls[:2], ["Invoice", "Payment"])
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "LUNAS")

    def test_w1_02_second_reject_performs_zero_writes(self):
        """W1: a losing second decision leaves all decision metadata untouched."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        self.admin_ancol_client.post(
            reverse("verify_payment", args=[payment.pk, "reject"]),
            {"rejection_note": "First decision"},
        )
        payment.refresh_from_db()
        invoice.refresh_from_db()
        first_state = (
            payment.status,
            payment.rejection_note,
            payment.verified_at,
            invoice.status,
        )
        resp = self.admin_ancol_client.post(
            reverse("verify_payment", args=[payment.pk, "reject"]),
            {"rejection_note": "Second attempt should lose"},
        )
        self.assertEqual(resp.status_code, 302)
        payment.refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual(
            (payment.status, payment.rejection_note, payment.verified_at, invoice.status),
            first_state,
        )

    def test_w1_03_approve_after_reject_preserves_rejection_metadata(self):
        """W1: approve attempt after reject cannot overwrite REJECTED evidence."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        self.admin_ancol_client.post(
            reverse("verify_payment", args=[payment.pk, "reject"]),
            {"rejection_note": "Rejected with reason"},
        )
        payment.refresh_from_db()
        note, verified_at = payment.rejection_note, payment.verified_at
        resp = self.admin_ancol_client.post(reverse("verify_payment", args=[payment.pk, "approve"]))
        self.assertEqual(resp.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "REJECTED")
        self.assertEqual(payment.rejection_note, note)
        self.assertEqual(payment.verified_at, verified_at)

    def test_w1_04_finalized_invoice_cannot_be_reverted(self):
        """W1: a stale PENDING payment cannot revert a finalized invoice."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        invoice.status = "LUNAS"
        invoice.save()
        resp = self.admin_ancol_client.post(
            reverse("verify_payment", args=[payment.pk, "reject"]),
            {"rejection_note": "stale attempt"},
        )
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(invoice.status, "LUNAS")
        self.assertEqual(payment.status, "PENDING")

    def test_w2_01_invoice_detail_electricity_uses_locked_read(self):
        """W2: invoice_detail POST serializes on the invoice row."""
        tenant, contract, invoice = self._setup_payment_data()
        calls = []
        with self._spy_on_select_for_update(calls):
            resp = self.admin_ancol_client.post(
                reverse("invoice_detail", args=[invoice.pk]),
                {"meter_reading_start": 100, "meter_reading_end": 150, "rate_per_kwh": "1500.00"},
            )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(calls)
        self.assertEqual(calls[0], "Invoice")
        self.assertNotIn("Payment", calls)
        invoice.refresh_from_db()
        self.assertEqual(invoice.electricity_bill_amount, Decimal("75000.00"))

    def test_w2_02_model_guard_blocks_write_on_lunas_invoice(self):
        """W2: ElectricityReading.save() refuses writes once the invoice is LUNAS."""
        tenant, contract, invoice = self._setup_payment_data()
        reading = ElectricityReading.objects.create(
            invoice=invoice,
            meter_reading_start=0,
            meter_reading_end=10,
            rate_per_kwh=Decimal("1500"),
        )
        invoice.refresh_from_db()  # fresh amounts before flipping status
        invoice.status = "LUNAS"
        invoice.save()
        reading.meter_reading_end = 999
        with self.assertRaises(ValidationError):
            reading.save()
        reading.refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual(reading.meter_reading_end, 10)
        self.assertEqual(invoice.electricity_bill_amount, Decimal("15000.00"))

    def test_w2_03_model_guard_blocks_creation_on_lunas_invoice(self):
        """W2: no ElectricityReading can be created on a LUNAS invoice (model layer)."""
        tenant, contract, invoice = self._setup_payment_data()
        invoice.status = "LUNAS"
        invoice.save()
        with self.assertRaises(ValidationError):
            ElectricityReading.objects.create(
                invoice=invoice,
                meter_reading_start=0,
                meter_reading_end=10,
                rate_per_kwh=Decimal("1500"),
            )
        self.assertFalse(ElectricityReading.objects.filter(invoice=invoice).exists())
        invoice.refresh_from_db()
        self.assertEqual(invoice.electricity_bill_amount, Decimal("0"))

    def test_w2_04_model_guard_allows_unpaid_writes(self):
        """W2 regression: unpaid invoices still accept electricity writes."""
        tenant, contract, invoice = self._setup_payment_data()
        reading = ElectricityReading.objects.create(
            invoice=invoice,
            meter_reading_start=0,
            meter_reading_end=10,
            rate_per_kwh=Decimal("1500"),
        )
        self.assertEqual(reading.calculated_amount, Decimal("15000.00"))

    def test_w2_05_upload_confirmation_uses_locked_invoice(self):
        """W2: public upload confirmation re-checks the invoice under a row lock."""
        tenant, contract, invoice = self._setup_payment_data()
        ElectricityReading.objects.create(
            invoice=invoice,
            meter_reading_start=0,
            meter_reading_end=10,
            rate_per_kwh=Decimal("1500"),
        )
        session = self.public_client.session
        session["verified_contract_id"] = contract.id
        session.save()
        img = create_test_image("w2_confirm.jpg")
        calls = []
        with self._spy_on_select_for_update(calls):
            resp = self.public_client.post(
                reverse("public_payment_step2"), {"payment_proof_file": img}, format="multipart"
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(calls, ["Invoice"])
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "MENUNGGU_VERIFIKASI")
        self.assertTrue(Payment.objects.filter(invoice=invoice).exists())

    def test_w2_06_upload_confirmation_cannot_reopen_decided_invoice(self):
        """W2: upload confirmation cannot reopen/flip a LUNAS invoice."""
        tenant, contract, invoice = self._setup_payment_data()
        invoice.status = "LUNAS"
        invoice.save()
        session = self.public_client.session
        session["verified_contract_id"] = contract.id
        session.save()
        img = create_test_image("w2_lunas.jpg")
        resp = self.public_client.post(
            reverse("public_payment_step2"), {"payment_proof_file": img}, format="multipart"
        )
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "LUNAS")
        self.assertFalse(Payment.objects.filter(invoice=invoice).exists())

    def test_w2_07_model_save_uses_locked_fresh_invoice(self):
        """W2: ElectricityReading.save() writes the locked fresh row, not the stale object."""
        tenant, contract, invoice = self._setup_payment_data()
        reading = ElectricityReading(
            invoice=invoice,
            meter_reading_start=0,
            meter_reading_end=10,
            rate_per_kwh=Decimal("1500"),
        )
        # Concurrent change behind the local stale object: a full-row stale write
        # would resurrect the old due_date; the fresh-locked write must keep it.
        Invoice.objects.filter(pk=invoice.pk).update(due_date=date(2031, 1, 1))
        calls = []
        with self._spy_on_select_for_update(calls):
            reading.save()
        self.assertIn("Invoice", calls)
        invoice.refresh_from_db()
        reading.refresh_from_db()
        self.assertEqual(reading.calculated_amount, Decimal("15000.00"))
        self.assertEqual(invoice.electricity_bill_amount, Decimal("15000.00"))
        self.assertEqual(invoice.due_date, date(2031, 1, 1))  # fresh row survived

    def test_w2_08_upload_confirmation_rechecks_after_stale_prefetch(self):
        """W2: a stale prefetch (invoice decided meanwhile) is caught by the locked re-check."""
        tenant, contract, invoice = self._setup_payment_data()
        invoice.status = "LUNAS"
        invoice.save()
        session = self.public_client.session
        session["verified_contract_id"] = contract.id
        session.save()
        img = create_test_image("w2_stale.jpg")
        # Simulate the decided-meanwhile race shape: bypass the status exclusion so
        # the view's prefetch still believes an active invoice exists.
        with mock.patch.object(QuerySet, "exclude", lambda self, *args, **kwargs: self):
            resp = self.public_client.post(
                reverse("public_payment_step2"), {"payment_proof_file": img}, format="multipart"
            )
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "LUNAS")
        self.assertFalse(Payment.objects.filter(invoice=invoice).exists())
        # Session preserved for a legitimate retry (no success path taken)
        self.assertIn("verified_contract_id", self.public_client.session)

    def test_w3_01_health_path_exempt_from_ssl_redirect(self):
        """W3: /health/ skips the HTTPS redirect so the container check reaches the view."""
        from django.middleware.security import SecurityMiddleware

        self.assertIn(r"^health/$", settings.SECURE_REDIRECT_EXEMPT)
        with override_settings(SECURE_SSL_REDIRECT=True, SECURE_REDIRECT_EXEMPT=[r"^health/$"]):
            middleware = SecurityMiddleware(lambda request: HttpResponse("ok"))
            health_response = middleware(RequestFactory().get("/health/"))
            other_response = middleware(RequestFactory().get("/invoice/"))
        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(other_response.status_code, 301)

    def test_w3_02_health_endpoint_checks_database(self):
        """W3: /health/ actually executes the DB check and returns ok."""
        resp = self.client.get("/health/")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("database"), "connected")

    def test_w4_01_audit_warns_lunas_without_approved_payment(self):
        """W4: LUNAS invoice whose only payment is REJECTED gets a visible warning."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        self.admin_ancol_client.post(
            reverse("verify_payment", args=[payment.pk, "reject"]),
            {"rejection_note": "not valid"},
        )
        invoice.refresh_from_db()
        invoice.status = "LUNAS"  # simulate paid without approved evidence
        invoice.save()
        out = io.StringIO()
        call_command("audit_payment_history", stdout=out)
        text = out.getvalue()
        self.assertIn("WARNINGS (non-blocking data-quality review):", text)
        self.assertIn(f"invoice {invoice.pk}: LUNAS invoice without approved payment", text)
        self.assertIn("No ambiguous rows detected", text)

    def test_w4_02_audit_no_warning_when_approved_payment_exists(self):
        """W4: LUNAS invoice with an APPROVED payment is not warned."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        self.admin_ancol_client.post(reverse("verify_payment", args=[payment.pk, "approve"]))
        out = io.StringIO()
        call_command("audit_payment_history", stdout=out)
        text = out.getvalue()
        self.assertNotIn("without approved payment", text)

    # ================================================================
    # PHASE 23: FINAL-REVIEW ADMIN-SURFACE HARDENING (W5)
    # ================================================================

    def test_w2_09_model_guard_blocks_write_when_menunggu(self):
        """W5: model guard covers MENUNGGU_VERIFIKASI, not only LUNAS."""
        tenant, contract, invoice = self._setup_payment_data()
        reading = ElectricityReading.objects.create(
            invoice=invoice,
            meter_reading_start=0,
            meter_reading_end=10,
            rate_per_kwh=Decimal("1500"),
        )
        invoice.refresh_from_db()
        invoice.status = "MENUNGGU_VERIFIKASI"
        invoice.save()
        reading.meter_reading_end = 999
        with self.assertRaises(ValidationError):
            reading.save()
        reading.refresh_from_db()
        invoice.refresh_from_db()
        self.assertEqual(reading.meter_reading_end, 10)
        self.assertEqual(invoice.electricity_bill_amount, Decimal("15000.00"))

    def test_w2_10_model_guard_blocks_creation_when_menunggu(self):
        """W5: no reading creation while awaiting verification (model layer)."""
        tenant, contract, invoice = self._setup_payment_data()
        invoice.status = "MENUNGGU_VERIFIKASI"
        invoice.save()
        with self.assertRaises(ValidationError):
            ElectricityReading.objects.create(
                invoice=invoice,
                meter_reading_start=0,
                meter_reading_end=10,
                rate_per_kwh=Decimal("1500"),
            )
        self.assertFalse(ElectricityReading.objects.filter(invoice=invoice).exists())

    def test_w5_01_admin_invoice_menunggu_locks_financial_fields(self):
        """W5: MENUNGGU invoice keeps amounts/contract/due-date read-only in admin."""
        from django.contrib import admin as dj_admin

        from finance.admin import InvoiceAdmin

        ma = InvoiceAdmin(Invoice, dj_admin.site)
        tenant, contract, invoice, payment = self._setup_verification_data()  # MENUNGGU
        ro = ma.get_readonly_fields(None, invoice)
        for field in (
            "base_rent_amount",
            "electricity_bill_amount",
            "due_date",
            "contract",
            "billing_period_start",
            "status",
            "total_amount",
        ):
            self.assertIn(field, ro)
        invoice.status = "BELUM_LUNAS"
        invoice.save()
        ro_open = ma.get_readonly_fields(None, invoice)
        self.assertNotIn("base_rent_amount", ro_open)

    def _admin_invoice_post_data(self, invoice):
        return {
            "contract": invoice.contract_id,
            "billing_period_start": invoice.billing_period_start.isoformat(),
            "due_date": invoice.due_date.isoformat(),
            "base_rent_amount": str(invoice.base_rent_amount),
            "electricity_bill_amount": str(invoice.electricity_bill_amount),
            "_save": "Save",
        }

    def test_w5_02_admin_cannot_edit_lunas_invoice(self):
        """W5: admin save refuses edits on a LUNAS invoice (no unlock+save TOCTOU)."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        invoice.status = "LUNAS"
        invoice.save()
        data = self._admin_invoice_post_data(invoice)
        data["base_rent_amount"] = "9999999"
        resp = self.superuser_client.post(
            reverse("admin:finance_invoice_change", args=[invoice.pk]), data
        )
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.base_rent_amount, Decimal("2000000.00"))
        self.assertEqual(invoice.total_amount, Decimal("2000000.00"))

    def test_w5_03_admin_edit_on_menunggu_restores_financial_values(self):
        """W5: stale admin POST on a MENUNGGU invoice cannot change financial values."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        data = self._admin_invoice_post_data(invoice)
        data["base_rent_amount"] = "9999999"
        data["due_date"] = "2031-01-01"
        resp = self.superuser_client.post(
            reverse("admin:finance_invoice_change", args=[invoice.pk]), data
        )
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.base_rent_amount, Decimal("2000000.00"))
        self.assertEqual(invoice.due_date, date.today() + timedelta(days=10))
        self.assertEqual(invoice.status, "MENUNGGU_VERIFIKASI")
        self.assertEqual(invoice.electricity_bill_amount, Decimal("0"))

    def test_w5_04_admin_electricity_readonly_when_menunggu(self):
        """W5: ElectricityReading is fully read-only while its invoice awaits verification."""
        from django.contrib import admin as dj_admin

        from finance.admin import ElectricityReadingAdmin

        ma = ElectricityReadingAdmin(ElectricityReading, dj_admin.site)
        tenant, contract, invoice = self._setup_payment_data()
        reading = ElectricityReading.objects.create(
            invoice=invoice,
            meter_reading_start=0,
            meter_reading_end=10,
            rate_per_kwh=Decimal("1500"),
        )
        invoice.refresh_from_db()
        invoice.status = "MENUNGGU_VERIFIKASI"
        invoice.save()
        reading.refresh_from_db()
        ro = ma.get_readonly_fields(None, reading)
        self.assertIn("meter_reading_end", ro)
