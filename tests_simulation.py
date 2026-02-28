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

import os
import io
import tempfile
from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.exceptions import ValidationError

from core.models import KostLocation, Room
from users.models import AdminProfile
from tenants.models import Tenant, TenantContract, MaintenanceTicket
from finance.models import Invoice, Payment, ElectricityReading, OperationCost

User = get_user_model()

# Disable file storage writes during test for speed
MEDIA_ROOT_TMP = tempfile.mkdtemp()


def create_test_image(name='test.jpg', size=(100, 100)):
    """Create a minimal valid JPEG file for upload testing."""
    from PIL import Image
    img = Image.new('RGB', size, color='red')
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)
    buf.name = name
    return buf


@override_settings(
    MEDIA_ROOT=MEDIA_ROOT_TMP,
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage',
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
            username='admin', password='admin123', email='admin@evy.id',
            first_name='Evy', last_name='Owner'
        )

        # 0.2 — Create Locations
        self.loc_ancol = KostLocation.objects.create(
            name='Kost Ancol', address='Jl. Pasir Putih, Ancol',
            electricity_rate_per_kwh=Decimal('1500.00')
        )
        self.loc_kana = KostLocation.objects.create(
            name='Kost Kana', address='Jl. Dago Pakar, Bandung',
            electricity_rate_per_kwh=Decimal('1700.00')
        )
        self.loc_uns = KostLocation.objects.create(
            name='Kost UNS', address='Jl. Ir Sutami, Solo',
            electricity_rate_per_kwh=Decimal('1300.00')
        )

        # 0.3 — Create Rooms (3 per location for testing)
        self.rooms = {}
        for loc, prefix, prices in [
            (self.loc_ancol, 'A', [1500000, 2000000, 1500000]),
            (self.loc_kana, 'K', [1500000, 1800000, 1500000]),
            (self.loc_uns, 'U', [1000000, 1500000, 1200000]),
        ]:
            for i, price in enumerate(prices, 1):
                room = Room.objects.create(
                    kost_location=loc,
                    room_number=f'{prefix}-10{i}',
                    price_monthly=Decimal(str(price)),
                    is_token_electricity=(prefix == 'K'),  # Kana = token
                    capacity=1
                )
                self.rooms[f'{prefix}-10{i}'] = room

        # 0.4 — Create Admin Staff Users
        self.admin_ancol = User.objects.create_user(
            username='admin_ancol', password='staff123', is_staff=True,
            first_name='Admin', last_name='Ancol'
        )
        AdminProfile.objects.create(user=self.admin_ancol, assigned_location=self.loc_ancol)

        self.admin_kana = User.objects.create_user(
            username='admin_kana', password='staff123', is_staff=True,
            first_name='Admin', last_name='Kana'
        )
        AdminProfile.objects.create(user=self.admin_kana, assigned_location=self.loc_kana)

        self.admin_uns = User.objects.create_user(
            username='admin_uns', password='staff123', is_staff=True,
            first_name='Admin', last_name='UNS'
        )
        AdminProfile.objects.create(user=self.admin_uns, assigned_location=self.loc_uns)

        self.plain_user = User.objects.create_user(
            username='plain_user', password='plain123', is_staff=False,
            first_name='Plain', last_name='User'
        )

        # Login all clients
        self.superuser_client.login(username='admin', password='admin123')
        self.admin_ancol_client.login(username='admin_ancol', password='staff123')
        self.admin_kana_client.login(username='admin_kana', password='staff123')
        self.admin_uns_client.login(username='admin_uns', password='staff123')
        self.plain_user_client.login(username='plain_user', password='plain123')

    # ================================================================
    # PHASE 0: INFRASTRUCTURE TESTS (F-45, F-46, F-01)
    # ================================================================
    def test_phase0_01_health_check(self):
        """F-45: Health check returns OK + DB connected."""
        resp = self.client.get('/health/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['database'], 'connected')

    def test_phase0_02_landing_page(self):
        """F-01: Landing page renders for anonymous user."""
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'home.html')

    def test_phase0_03_landing_redirect_logged_in(self):
        """F-01: Landing page redirects to dashboard for logged-in user."""
        resp = self.superuser_client.get('/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('dashboard', resp.url)

    def test_phase0_04_django_admin(self):
        """F-46: Django admin panel accessible by superuser."""
        resp = self.superuser_client.get('/sekretariat-evykost/')
        self.assertEqual(resp.status_code, 200)

    # ================================================================
    # PHASE 1: AUTH & STAFF MANAGEMENT
    # ================================================================
    def test_phase1_01_login_page(self):
        """F-08: Login page renders."""
        resp = self.client.get('/accounts/login/')
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'auth/login.html')

    def test_phase1_02_login_success(self):
        """F-08: Superuser login succeeds."""
        c = Client()
        resp = c.post('/accounts/login/', {'username': 'admin', 'password': 'admin123'})
        self.assertEqual(resp.status_code, 302)  # Redirect to next/dashboard

    def test_phase1_03_login_fail(self):
        """F-08: Wrong password stays on login page."""
        c = Client()
        resp = c.post('/accounts/login/', {'username': 'admin', 'password': 'wrong'})
        self.assertEqual(resp.status_code, 200)  # Stays on login

    def test_phase1_04_logout(self):
        """F-09: Logout redirects to login."""
        c = Client()
        c.login(username='admin', password='admin123')
        resp = c.post('/accounts/logout/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url)

    def test_phase1_05_staff_list_superuser(self):
        """F-39: Superuser sees staff list."""
        resp = self.superuser_client.get(reverse('staff_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'admin_ancol')

    def test_phase1_06_staff_list_admin_forbidden(self):
        """F-39: Non-superuser redirected from staff list."""
        resp = self.admin_ancol_client.get(reverse('staff_list'))
        self.assertEqual(resp.status_code, 302)

    def test_phase1_07_staff_create(self):
        """F-40: Superuser creates a new staff."""
        resp = self.superuser_client.post(reverse('staff_add'), {
            'username': 'admin_test',
            'password1': 'TestPass123!',
            'password2': 'TestPass123!',
            'first_name': 'Test',
            'last_name': 'Admin',
            'email': 'test@evy.id',
            'assigned_location': self.loc_ancol.pk,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(username='admin_test').exists())
        new_user = User.objects.get(username='admin_test')
        self.assertTrue(new_user.is_staff)
        self.assertEqual(new_user.admin_profile.assigned_location, self.loc_ancol)

    def test_phase1_08_staff_update(self):
        """F-41: Superuser edits staff data."""
        resp = self.superuser_client.post(
            reverse('staff_edit', args=[self.admin_ancol.pk]),
            {
                'first_name': 'Updated',
                'last_name': 'Ancol',
                'email': 'updated@evy.id',
                'is_active': True,
                'assigned_location': self.loc_ancol.pk,
            }
        )
        self.assertEqual(resp.status_code, 302)
        self.admin_ancol.refresh_from_db()
        self.assertEqual(self.admin_ancol.first_name, 'Updated')

    def test_phase1_09_password_change_page(self):
        """F-10: Password change page renders for logged-in user."""
        resp = self.admin_ancol_client.get(reverse('password_change'))
        self.assertEqual(resp.status_code, 200)

    # ================================================================
    # PHASE 2: LOCATION MANAGEMENT
    # ================================================================
    def test_phase2_01_location_list_superuser(self):
        """F-13: Superuser sees all locations."""
        resp = self.superuser_client.get(reverse('location_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Kost Ancol')
        self.assertContains(resp, 'Kost Kana')
        self.assertContains(resp, 'Kost UNS')

    def test_phase2_02_location_list_admin_redirect(self):
        """F-13: Admin biasa gets redirected to own location edit."""
        resp = self.admin_ancol_client.get(reverse('location_list'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(str(self.loc_ancol.pk), resp.url)

    def test_phase2_03_location_update_superuser(self):
        """F-14: Superuser edits location tariff."""
        resp = self.superuser_client.post(
            reverse('location_update', args=[self.loc_ancol.pk]),
            {
                'name': 'Kost Ancol',
                'address': 'Jl. Pasir Putih, Ancol',
                'electricity_rate_per_kwh': '1600.00',
                'description': 'Updated by superuser',
            }
        )
        self.assertEqual(resp.status_code, 302)
        self.loc_ancol.refresh_from_db()
        self.assertEqual(self.loc_ancol.electricity_rate_per_kwh, Decimal('1600.00'))

    def test_phase2_04_location_update_admin_own(self):
        """F-14: Admin edits own location."""
        resp = self.admin_ancol_client.post(
            reverse('location_update', args=[self.loc_ancol.pk]),
            {
                'name': 'Kost Ancol',
                'address': 'Jl. Pasir Putih Baru, Ancol',
                'electricity_rate_per_kwh': '1500.00',
                'description': '',
            }
        )
        self.assertEqual(resp.status_code, 302)

    def test_phase2_05_location_update_admin_other_forbidden(self):
        """F-14 Security: Admin cannot edit other location."""
        resp = self.admin_ancol_client.post(
            reverse('location_update', args=[self.loc_kana.pk]),
            {
                'name': 'Hacked', 'address': 'Hacked',
                'electricity_rate_per_kwh': '9999',
                'description': '',
            }
        )
        self.assertEqual(resp.status_code, 302)
        self.loc_kana.refresh_from_db()
        self.assertNotEqual(self.loc_kana.name, 'Hacked')

    # ================================================================
    # PHASE 3: ROOM MANAGEMENT
    # ================================================================
    def test_phase3_01_room_list(self):
        """F-15: Admin sees only rooms at their location."""
        resp = self.admin_ancol_client.get(reverse('room_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'A-101')
        self.assertNotContains(resp, 'K-101')

    def test_phase3_02_room_list_superuser_all(self):
        """F-15: Superuser sees all rooms."""
        resp = self.superuser_client.get(reverse('room_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'A-101')
        self.assertContains(resp, 'K-101')
        self.assertContains(resp, 'U-101')

    def test_phase3_03_room_create(self):
        """F-16: Admin creates a room."""
        resp = self.admin_ancol_client.post(reverse('room_add'), {
            'kost_location': self.loc_ancol.pk,
            'room_number': 'A-201',
            'price_monthly': '1800000',
            'is_token_electricity': False,
            'capacity': 1,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Room.objects.filter(room_number='A-201').exists())

    def test_phase3_04_room_update(self):
        """F-17: Admin edits room price."""
        room = self.rooms['A-101']
        resp = self.admin_ancol_client.post(
            reverse('room_edit', args=[room.pk]),
            {
                'kost_location': self.loc_ancol.pk,
                'room_number': 'A-101',
                'price_monthly': '1900000',
                'is_token_electricity': False,
                'capacity': 1,
            }
        )
        self.assertEqual(resp.status_code, 302)
        room.refresh_from_db()
        self.assertEqual(room.price_monthly, Decimal('1900000'))

    def test_phase3_05_room_delete_empty(self):
        """F-18: Admin deletes empty room."""
        room = Room.objects.create(
            kost_location=self.loc_ancol, room_number='A-999',
            price_monthly=Decimal('1000000'), capacity=1
        )
        resp = self.admin_ancol_client.post(reverse('room_delete', args=[room.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Room.objects.filter(room_number='A-999').exists())

    def test_phase3_06_room_delete_occupied_fails(self):
        """F-18: Cannot delete room with active tenant."""
        room = self.rooms['A-101']
        tenant = Tenant.objects.create(
            full_name='Temp Test', phone_number='081', emergency_contact_phone='082'
        )
        TenantContract.objects.create(
            tenant=tenant, room=room, start_date=date.today(),
            monthly_rent_amount=room.price_monthly, is_active=True
        )
        resp = self.admin_ancol_client.post(reverse('room_delete', args=[room.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Room.objects.filter(pk=room.pk).exists())
        # Cleanup
        TenantContract.objects.filter(tenant=tenant).delete()
        tenant.delete()

    def test_phase3_07_room_cross_location_forbidden(self):
        """F-17 Security: Admin Ancol cannot edit Kana room."""
        kana_room = self.rooms['K-101']
        resp = self.admin_ancol_client.post(
            reverse('room_edit', args=[kana_room.pk]),
            {
                'kost_location': self.loc_kana.pk,
                'room_number': 'K-101',
                'price_monthly': '9999999',
                'capacity': 1,
            }
        )
        self.assertEqual(resp.status_code, 302)
        kana_room.refresh_from_db()
        self.assertNotEqual(kana_room.price_monthly, Decimal('9999999'))

    def test_phase3_08_room_list_natural_ordering(self):
        """UI data order: room numbers should use natural sort (2 before 10)."""
        Room.objects.create(
            kost_location=self.loc_ancol,
            room_number='2',
            price_monthly=Decimal('1200000'),
            capacity=1,
        )
        Room.objects.create(
            kost_location=self.loc_ancol,
            room_number='10',
            price_monthly=Decimal('1200000'),
            capacity=1,
        )

        resp = self.admin_ancol_client.get(reverse('room_list'))
        self.assertEqual(resp.status_code, 200)

        ordered_numbers = [room.room_number for room in resp.context['rooms']]
        self.assertLess(ordered_numbers.index('2'), ordered_numbers.index('10'))

    # ================================================================
    # PHASE 4: TENANT ONBOARDING
    # ================================================================
    def test_phase4_01_tenant_list(self):
        """F-19: Tenant list renders with KPI."""
        resp = self.admin_ancol_client.get(reverse('tenant_list'))
        self.assertEqual(resp.status_code, 200)

    def test_phase4_02_tenant_create(self):
        """F-20: Admin creates a new tenant."""
        resp = self.admin_ancol_client.post(reverse('tenant_add'), {
            'full_name': 'Budi Santoso',
            'phone_number': '081234567890',
            'emergency_contact_phone': '089876543210',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Tenant.objects.filter(full_name='Budi Santoso').exists())

    def test_phase4_03_tenant_update(self):
        """F-21: Admin edits tenant data."""
        tenant = Tenant.objects.create(
            full_name='Edit Me', phone_number='081',
            emergency_contact_phone='082'
        )
        # Tenant needs a contract at Ancol for admin_ancol to access
        TenantContract.objects.create(
            tenant=tenant, room=self.rooms['A-102'],
            start_date=date.today(), monthly_rent_amount=Decimal('2000000')
        )
        resp = self.admin_ancol_client.post(
            reverse('tenant_edit', args=[tenant.pk]),
            {
                'full_name': 'Edited Name',
                'phone_number': '081999',
                'emergency_contact_phone': '082999',
            }
        )
        self.assertEqual(resp.status_code, 302)
        tenant.refresh_from_db()
        self.assertEqual(tenant.full_name, 'Edited Name')

    def test_phase4_04_tenant_search(self):
        """F-19: Search filters tenants."""
        Tenant.objects.create(
            full_name='Searchable Person', phone_number='081',
            emergency_contact_phone='082'
        )
        resp = self.superuser_client.get(reverse('tenant_list') + '?q=Searchable')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Searchable Person')

    def test_phase4_05_assign_room(self):
        """F-22: Admin assigns room to tenant, PIN auto-generated."""
        tenant = Tenant.objects.create(
            full_name='Assign Test', phone_number='081',
            emergency_contact_phone='082'
        )
        resp = self.admin_ancol_client.post(
            reverse('tenant_assign_room', args=[tenant.pk]),
            {
                'room': self.rooms['A-101'].pk,
                'start_date': date.today().isoformat(),
                'monthly_rent_amount': '1500000',
            }
        )
        self.assertEqual(resp.status_code, 302)
        contract = TenantContract.objects.filter(tenant=tenant, is_active=True).first()
        self.assertIsNotNone(contract)
        self.assertEqual(len(contract.payment_pin), 6)
        self.assertTrue(contract.payment_pin.isdigit())

    def test_phase4_06_double_assign_prevented(self):
        """F-22 Security: Cannot assign room if tenant already has active contract."""
        tenant = Tenant.objects.create(
            full_name='Double Test', phone_number='081',
            emergency_contact_phone='082'
        )
        TenantContract.objects.create(
            tenant=tenant, room=self.rooms['A-103'],
            start_date=date.today(), monthly_rent_amount=Decimal('1500000')
        )
        # Try to assign again
        resp = self.admin_ancol_client.post(
            reverse('tenant_assign_room', args=[tenant.pk]),
            {
                'room': self.rooms['A-102'].pk,
                'start_date': date.today().isoformat(),
                'monthly_rent_amount': '1500000',
            }
        )
        # Should redirect with error (not create second contract)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            TenantContract.objects.filter(tenant=tenant, is_active=True).count(), 1
        )

    # ================================================================
    # PHASE 5: DASHBOARD
    # ================================================================
    def test_phase5_01_dashboard_superuser(self):
        """F-12: Superuser dashboard with location filter."""
        resp = self.superuser_client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Semua Lokasi')

    def test_phase5_02_dashboard_superuser_filter(self):
        """F-12: Superuser filters by location."""
        resp = self.superuser_client.get(
            reverse('dashboard') + f'?location={self.loc_ancol.pk}'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Kost Ancol')

    def test_phase5_03_dashboard_admin(self):
        """F-12: Admin sees only their location."""
        resp = self.admin_ancol_client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Kost Ancol')

    def test_phase5_04_dashboard_invalid_location(self):
        """F-12: Invalid location ID doesn't crash (B-02 fix)."""
        resp = self.superuser_client.get(reverse('dashboard') + '?location=abc')
        self.assertEqual(resp.status_code, 200)

    # ================================================================
    # PHASE 6: BILLING CYCLE
    # ================================================================
    def _setup_billing_data(self):
        """Helper: Create tenant with contract for billing tests."""
        tenant = Tenant.objects.create(
            full_name='Billing Tenant', phone_number='081',
            emergency_contact_phone='082'
        )
        contract = TenantContract.objects.create(
            tenant=tenant, room=self.rooms['A-101'],
            start_date=date.today() - timedelta(days=30),
            monthly_rent_amount=Decimal('1500000')
        )
        return tenant, contract

    def test_phase6_01_generate_invoices_bulk(self):
        """F-28: Generate bulk invoices creates new invoices."""
        tenant, contract = self._setup_billing_data()
        resp = self.admin_ancol_client.post(reverse('invoice_generate_bulk'))
        self.assertEqual(resp.status_code, 302)
        # Should have created at least 1 invoice
        self.assertTrue(Invoice.objects.filter(contract=contract).exists())

    def test_phase6_02_generate_invoices_idempotent(self):
        """F-28: Generate twice doesn't create duplicates."""
        tenant, contract = self._setup_billing_data()
        self.admin_ancol_client.post(reverse('invoice_generate_bulk'))
        count_first = Invoice.objects.filter(contract=contract).count()
        self.admin_ancol_client.post(reverse('invoice_generate_bulk'))
        count_second = Invoice.objects.filter(contract=contract).count()
        self.assertEqual(count_first, count_second)

    def test_phase6_03_invoice_list(self):
        """F-25: Invoice list renders with pagination."""
        tenant, contract = self._setup_billing_data()
        Invoice.objects.create(
            contract=contract, billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal('1500000'), electricity_bill_amount=0,
            total_amount=Decimal('1500000'), status='BELUM_LUNAS'
        )
        resp = self.admin_ancol_client.get(reverse('invoice_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Billing Tenant')

    def test_phase6_04_invoice_list_filter_status(self):
        """F-25: Filter invoices by status."""
        tenant, contract = self._setup_billing_data()
        Invoice.objects.create(
            contract=contract, billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal('1500000'), electricity_bill_amount=0,
            total_amount=Decimal('1500000'), status='BELUM_LUNAS'
        )
        resp = self.admin_ancol_client.get(reverse('invoice_list') + '?status=LUNAS')
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'Billing Tenant')

    def test_phase6_05_invoice_list_search(self):
        """F-25: Search invoices by tenant name."""
        tenant, contract = self._setup_billing_data()
        Invoice.objects.create(
            contract=contract, billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal('1500000'), electricity_bill_amount=0,
            total_amount=Decimal('1500000'), status='BELUM_LUNAS'
        )
        resp = self.admin_ancol_client.get(reverse('invoice_list') + '?q=Billing')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Billing Tenant')

    def test_phase6_05b_invoice_list_auto_sync_overdue_status(self):
        """Invoice list auto-updates BELUM_LUNAS overdue invoices to TELAT_BAYAR."""
        tenant, contract = self._setup_billing_data()
        invoice = Invoice.objects.create(
            contract=contract,
            billing_period_start=date.today() - timedelta(days=35),
            due_date=date.today() - timedelta(days=3),
            base_rent_amount=Decimal('1500000'),
            electricity_bill_amount=0,
            total_amount=Decimal('1500000'),
            status='BELUM_LUNAS'
        )

        resp = self.admin_ancol_client.get(reverse('invoice_list'))
        self.assertEqual(resp.status_code, 200)

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'TELAT_BAYAR')

    def test_phase6_06_invoice_detail_and_electricity(self):
        """F-26: Input electricity meter reading updates invoice total."""
        tenant, contract = self._setup_billing_data()
        invoice = Invoice.objects.create(
            contract=contract, billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal('1500000'), electricity_bill_amount=0,
            total_amount=Decimal('1500000'), status='BELUM_LUNAS'
        )
        # GET detail page
        resp = self.admin_ancol_client.get(reverse('invoice_detail', args=[invoice.pk]))
        self.assertEqual(resp.status_code, 200)

        # POST electricity reading
        resp = self.admin_ancol_client.post(
            reverse('invoice_detail', args=[invoice.pk]),
            {
                'meter_reading_start': 1000,
                'meter_reading_end': 1150,
                'rate_per_kwh': '1500.00',
            }
        )
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        # 150 kwh * 1500 = 225,000
        self.assertEqual(invoice.electricity_bill_amount, Decimal('225000.00'))
        self.assertEqual(invoice.total_amount, Decimal('1725000.00'))

    def test_phase6_07_electricity_validation(self):
        """F-26: Electricity meter end < start fails validation (D-02 fix)."""
        tenant, contract = self._setup_billing_data()
        invoice = Invoice.objects.create(
            contract=contract, billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal('1500000'), electricity_bill_amount=0,
            total_amount=Decimal('1500000'), status='BELUM_LUNAS'
        )
        resp = self.admin_ancol_client.post(
            reverse('invoice_detail', args=[invoice.pk]),
            {
                'meter_reading_start': 1150,
                'meter_reading_end': 1000,  # End < Start!
                'rate_per_kwh': '1500.00',
            }
        )
        # Should stay on page (200) with error, not redirect
        self.assertEqual(resp.status_code, 200)
        # No electricity reading should be saved
        self.assertFalse(ElectricityReading.objects.filter(invoice=invoice).exists())

    def test_phase6_08_invoice_cross_location_forbidden(self):
        """F-26 Security: Admin cannot view invoice at other location."""
        tenant = Tenant.objects.create(
            full_name='Kana Tenant', phone_number='081',
            emergency_contact_phone='082'
        )
        contract = TenantContract.objects.create(
            tenant=tenant, room=self.rooms['K-101'],
            start_date=date.today(), monthly_rent_amount=Decimal('1500000')
        )
        invoice = Invoice.objects.create(
            contract=contract, billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal('1500000'), electricity_bill_amount=0,
            total_amount=Decimal('1500000'), status='BELUM_LUNAS'
        )
        # Admin Ancol tries to access Kana invoice
        resp = self.admin_ancol_client.get(reverse('invoice_detail', args=[invoice.pk]))
        self.assertEqual(resp.status_code, 302)

    def test_phase6_09_management_command_update_overdue(self):
        """F-44: update_overdue command changes BELUM_LUNAS → TELAT_BAYAR."""
        tenant, contract = self._setup_billing_data()
        invoice = Invoice.objects.create(
            contract=contract, billing_period_start=date.today() - timedelta(days=30),
            due_date=date.today() - timedelta(days=5),  # Already overdue
            base_rent_amount=Decimal('1500000'), electricity_bill_amount=0,
            total_amount=Decimal('1500000'), status='BELUM_LUNAS'
        )
        call_command('update_overdue')
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'TELAT_BAYAR')

    def test_phase6_10_management_command_generate_monthly(self):
        """F-43: generate_monthly_invoices command creates invoices."""
        tenant, contract = self._setup_billing_data()
        call_command('generate_monthly_invoices')
        # Should have created invoice for next month
        self.assertTrue(Invoice.objects.filter(contract=contract).exists())

    def test_phase6_11_ancol_billing_rule(self):
        """Business Rule B1: Ancol billing uses tenant's start_date.day."""
        tenant, contract = self._setup_billing_data()
        self.admin_ancol_client.post(reverse('invoice_generate_bulk'))
        invoice = Invoice.objects.filter(contract=contract).first()
        self.assertIsNotNone(invoice)
        # Due date should equal billing_period_start for Ancol
        self.assertEqual(invoice.due_date, invoice.billing_period_start)

    def test_phase6_12_non_ancol_billing_rule(self):
        """Business Rule B1: Non-Ancol billing uses fixed day 1 + 10 days."""
        tenant = Tenant.objects.create(
            full_name='UNS Tenant', phone_number='081',
            emergency_contact_phone='082'
        )
        contract = TenantContract.objects.create(
            tenant=tenant, room=self.rooms['U-101'],
            start_date=date.today() - timedelta(days=15),
            monthly_rent_amount=Decimal('1000000')
        )
        self.admin_uns_client.post(reverse('invoice_generate_bulk'))
        invoice = Invoice.objects.filter(contract=contract).first()
        self.assertIsNotNone(invoice)
        # Billing start should be day 1
        self.assertEqual(invoice.billing_period_start.day, 1)
        # Due date should be billing_start + 10
        expected_due = invoice.billing_period_start + timedelta(days=10)
        self.assertEqual(invoice.due_date, expected_due)

    # ================================================================
    # PHASE 7: PUBLIC PAYMENT PORTAL
    # ================================================================
    def _setup_payment_data(self):
        """Helper: Create full tenant+contract+invoice for payment flow."""
        tenant = Tenant.objects.create(
            full_name='Payment Tenant', phone_number='081',
            emergency_contact_phone='082'
        )
        contract = TenantContract.objects.create(
            tenant=tenant, room=self.rooms['A-102'],
            start_date=date.today() - timedelta(days=30),
            monthly_rent_amount=Decimal('2000000')
        )
        invoice = Invoice.objects.create(
            contract=contract, billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal('2000000'), electricity_bill_amount=0,
            total_amount=Decimal('2000000'), status='BELUM_LUNAS'
        )
        return tenant, contract, invoice

    def test_phase7_01_public_step1_page(self):
        """F-02: PIN validation page renders."""
        resp = self.public_client.get(reverse('public_payment_step1'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'finance/step1_pin.html')

    def test_phase7_02_public_step1_wrong_pin(self):
        """F-02: Wrong PIN shows error."""
        tenant, contract, invoice = self._setup_payment_data()
        resp = self.public_client.post(reverse('public_payment_step1'), {
            'kost_location': self.loc_ancol.pk,
            'room_number': 'A-102',
            'pin': '000000',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'PIN salah')

    def test_phase7_03_public_step1_success(self):
        """F-02: Correct PIN creates session and redirects."""
        tenant, contract, invoice = self._setup_payment_data()
        resp = self.public_client.post(reverse('public_payment_step1'), {
            'kost_location': self.loc_ancol.pk,
            'room_number': 'A-102',
            'pin': contract.payment_pin,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn('upload', resp.url)
        self.assertEqual(
            self.public_client.session['verified_contract_id'], contract.id
        )

    def test_phase7_04_public_step2_no_session(self):
        """F-03: Upload page without session redirects to PIN."""
        resp = self.public_client.get(reverse('public_payment_step2'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('bayar', resp.url)

    def test_phase7_05_public_step2_page(self):
        """F-03: Upload page shows invoice info."""
        tenant, contract, invoice = self._setup_payment_data()
        # Login via PIN first
        self.public_client.post(reverse('public_payment_step1'), {
            'kost_location': self.loc_ancol.pk,
            'room_number': 'A-102',
            'pin': contract.payment_pin,
        })
        resp = self.public_client.get(reverse('public_payment_step2'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Payment Tenant')

    def test_phase7_06_public_upload_payment(self):
        """F-03: Upload payment proof changes invoice status."""
        tenant, contract, invoice = self._setup_payment_data()
        # Login via PIN
        self.public_client.post(reverse('public_payment_step1'), {
            'kost_location': self.loc_ancol.pk,
            'room_number': 'A-102',
            'pin': contract.payment_pin,
        })
        # Upload proof
        img = create_test_image()
        resp = self.public_client.post(
            reverse('public_payment_step2'),
            {'payment_proof_file': img},
            format='multipart'
        )
        self.assertEqual(resp.status_code, 200)  # success.html rendered
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'MENUNGGU_VERIFIKASI')
        self.assertTrue(Payment.objects.filter(invoice=invoice).exists())

    def test_phase7_07_public_payment_history(self):
        """F-04: Payment history shows invoices with pagination."""
        tenant, contract, invoice = self._setup_payment_data()
        # Login via PIN
        session = self.public_client.session
        session['verified_contract_id'] = contract.id
        session.save()
        resp = self.public_client.get(reverse('public_payment_history'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Payment Tenant')

    def test_phase7_08_public_payment_history_no_session(self):
        """F-04: Payment history without session redirects."""
        resp = self.public_client.get(reverse('public_payment_history'))
        self.assertEqual(resp.status_code, 302)

    def test_phase7_09_public_logout(self):
        """F-05: Public logout clears session."""
        tenant, contract, invoice = self._setup_payment_data()
        session = self.public_client.session
        session['verified_contract_id'] = contract.id
        session.save()
        resp = self.public_client.get(reverse('public_logout'))
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('verified_contract_id', self.public_client.session)

    # ================================================================
    # PHASE 8: PAYMENT VERIFICATION
    # ================================================================
    def _setup_verification_data(self):
        """Helper: Create payment awaiting verification."""
        tenant, contract, invoice = self._setup_payment_data()
        invoice.status = 'MENUNGGU_VERIFIKASI'
        invoice.save()
        payment = Payment.objects.create(
            invoice=invoice,
            payment_proof_file='payment_proofs/test.jpg'
        )
        return tenant, contract, invoice, payment

    def test_phase8_01_approve_payment(self):
        """F-29: Admin approves payment → invoice LUNAS."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        resp = self.admin_ancol_client.post(
            reverse('verify_payment', args=[payment.pk, 'approve'])
        )
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'LUNAS')
        payment.refresh_from_db()
        self.assertIsNotNone(payment.verified_by)
        self.assertIsNotNone(payment.verified_at)

    def test_phase8_02_reject_payment(self):
        """F-30: Admin rejects payment → invoice reverts status."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        resp = self.admin_ancol_client.post(
            reverse('verify_payment', args=[payment.pk, 'reject']),
            {'rejection_note': 'Bukti tidak jelas'}
        )
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        # Due date is in the future, so should be BELUM_LUNAS
        self.assertIn(invoice.status, ['BELUM_LUNAS', 'TELAT_BAYAR'])
        payment.refresh_from_db()
        self.assertIn('Bukti tidak jelas', payment.rejection_note)

    def test_phase8_03_reject_overdue_payment(self):
        """F-30: Reject payment on overdue invoice → TELAT_BAYAR."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        invoice.due_date = date.today() - timedelta(days=5)
        invoice.save()
        resp = self.admin_ancol_client.post(
            reverse('verify_payment', args=[payment.pk, 'reject']),
            {'rejection_note': 'Wrong amount'}
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'TELAT_BAYAR')

    def test_phase8_04_verify_cross_location_forbidden(self):
        """F-29 Security: Admin cannot verify payment at other location."""
        tenant = Tenant.objects.create(
            full_name='Cross Test', phone_number='081',
            emergency_contact_phone='082'
        )
        contract = TenantContract.objects.create(
            tenant=tenant, room=self.rooms['K-101'],
            start_date=date.today(), monthly_rent_amount=Decimal('1500000')
        )
        invoice = Invoice.objects.create(
            contract=contract, billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal('1500000'), electricity_bill_amount=0,
            total_amount=Decimal('1500000'), status='MENUNGGU_VERIFIKASI'
        )
        payment = Payment.objects.create(
            invoice=invoice, payment_proof_file='payment_proofs/test.jpg'
        )
        # Admin Ancol tries to approve Kana payment
        resp = self.admin_ancol_client.post(
            reverse('verify_payment', args=[payment.pk, 'approve'])
        )
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'MENUNGGU_VERIFIKASI')  # Not changed

    def test_phase8_05_verify_invalid_action(self):
        """F-29 Validation: Invalid action is rejected (F-03 fix)."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        resp = self.admin_ancol_client.post(
            reverse('verify_payment', args=[payment.pk, 'invalid_action'])
        )
        self.assertEqual(resp.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'MENUNGGU_VERIFIKASI')

    def test_phase8_06_print_receipt_lunas(self):
        """F-27: Print receipt for LUNAS invoice."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        invoice.status = 'LUNAS'
        invoice.save()
        resp = self.admin_ancol_client.get(reverse('print_receipt', args=[invoice.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'finance/print_receipt.html')

    def test_phase8_07_print_receipt_not_lunas_fails(self):
        """F-27: Cannot print receipt for non-LUNAS invoice."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        resp = self.admin_ancol_client.get(reverse('print_receipt', args=[invoice.pk]))
        self.assertEqual(resp.status_code, 302)  # Redirect with error

    # ================================================================
    # PHASE 9: MAINTENANCE TICKETS
    # ================================================================
    def _setup_maintenance_data(self):
        """Helper: Create session-authenticated public client with contract."""
        tenant = Tenant.objects.create(
            full_name='Maintenance Tenant', phone_number='081',
            emergency_contact_phone='082'
        )
        contract = TenantContract.objects.create(
            tenant=tenant, room=self.rooms['A-103'],
            start_date=date.today(), monthly_rent_amount=Decimal('1500000')
        )
        # Set session for public client
        session = self.public_client.session
        session['verified_contract_id'] = contract.id
        session.save()
        return tenant, contract

    def test_phase9_01_report_create_page(self):
        """F-06: Report form renders with session."""
        tenant, contract = self._setup_maintenance_data()
        resp = self.public_client.get(reverse('public_report_create'))
        self.assertEqual(resp.status_code, 200)

    def test_phase9_02_report_create_no_session(self):
        """F-06: No session redirects to PIN."""
        c = Client()
        resp = c.get(reverse('public_report_create'))
        self.assertEqual(resp.status_code, 302)

    def test_phase9_03_report_submit(self):
        """F-06: Submit maintenance report creates ticket."""
        tenant, contract = self._setup_maintenance_data()
        resp = self.public_client.post(reverse('public_report_create'), {
            'title': 'Kran Bocor',
            'priority': 'HIGH',
            'description': 'Kran di kamar mandi bocor deras',
        })
        self.assertEqual(resp.status_code, 302)
        ticket = MaintenanceTicket.objects.filter(contract=contract).first()
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.title, 'Kran Bocor')
        self.assertEqual(ticket.status, 'PENDING')

    def test_phase9_04_report_list(self):
        """F-07: Report list shows tickets."""
        tenant, contract = self._setup_maintenance_data()
        MaintenanceTicket.objects.create(
            contract=contract, title='Test Ticket',
            description='Test', priority='MEDIUM'
        )
        resp = self.public_client.get(reverse('public_report_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Test Ticket')

    def test_phase9_05_admin_ticket_list(self):
        """F-35: Admin sees tickets at their location."""
        tenant, contract = self._setup_maintenance_data()
        MaintenanceTicket.objects.create(
            contract=contract, title='Admin View Ticket',
            description='Test', priority='HIGH'
        )
        resp = self.admin_ancol_client.get(reverse('ticket_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Admin View Ticket')

    def test_phase9_06_admin_ticket_filter_status(self):
        """F-35: Filter tickets by status."""
        tenant, contract = self._setup_maintenance_data()
        MaintenanceTicket.objects.create(
            contract=contract, title='Pending Ticket',
            description='Test', priority='LOW', status='PENDING'
        )
        resp = self.admin_ancol_client.get(
            reverse('ticket_list') + '?status=SELESAI'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'Pending Ticket')

    def test_phase9_07_admin_ticket_update_proses(self):
        """F-36: Admin updates ticket to PROSES."""
        tenant, contract = self._setup_maintenance_data()
        ticket = MaintenanceTicket.objects.create(
            contract=contract, title='Handlable',
            description='Test', priority='MEDIUM'
        )
        resp = self.admin_ancol_client.post(
            reverse('ticket_update', args=[ticket.pk]),
            {'status': 'PROSES'}
        )
        self.assertEqual(resp.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, 'PROSES')
        self.assertIsNone(ticket.completion_date)

    def test_phase9_08_admin_ticket_update_selesai(self):
        """F-36: Admin updates ticket to SELESAI with completion_date."""
        tenant, contract = self._setup_maintenance_data()
        ticket = MaintenanceTicket.objects.create(
            contract=contract, title='Fixable',
            description='Test', priority='MEDIUM', status='PROSES'
        )
        resp = self.admin_ancol_client.post(
            reverse('ticket_update', args=[ticket.pk]),
            {'status': 'SELESAI'}
        )
        self.assertEqual(resp.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, 'SELESAI')
        self.assertIsNotNone(ticket.completion_date)

    def test_phase9_09_admin_ticket_invalid_status(self):
        """F-36: Invalid status is rejected (H-01 fix)."""
        tenant, contract = self._setup_maintenance_data()
        ticket = MaintenanceTicket.objects.create(
            contract=contract, title='No Hack',
            description='Test', priority='MEDIUM'
        )
        resp = self.admin_ancol_client.post(
            reverse('ticket_update', args=[ticket.pk]),
            {'status': 'HACKED_STATUS'}
        )
        self.assertEqual(resp.status_code, 302)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, 'PENDING')  # Unchanged

    def test_phase9_10_admin_ticket_detail_page(self):
        """F-36: Ticket detail page renders on GET."""
        tenant, contract = self._setup_maintenance_data()
        ticket = MaintenanceTicket.objects.create(
            contract=contract, title='Detail View',
            description='Test detail', priority='LOW'
        )
        resp = self.admin_ancol_client.get(
            reverse('ticket_update', args=[ticket.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Detail View')

    # ================================================================
    # PHASE 10: OPERATIONAL COSTS
    # ================================================================
    def test_phase10_01_operation_list(self):
        """F-31: Operation list page renders."""
        resp = self.admin_ancol_client.get(reverse('operation_list'))
        self.assertEqual(resp.status_code, 200)

    def test_phase10_02_operation_create(self):
        """F-32: Admin creates operational cost."""
        img = create_test_image('nota.jpg')
        resp = self.admin_ancol_client.post(reverse('operation_add'), {
            'kost_location': self.loc_ancol.pk,
            'category': 'LISTRIK',
            'amount': '2500000',
            'incurred_date': date.today().isoformat(),
            'description': 'Bayar listrik bulanan PLN',
            'proof_file': img,
        })
        self.assertEqual(resp.status_code, 302)
        cost = OperationCost.objects.filter(category='LISTRIK').first()
        self.assertIsNotNone(cost)
        self.assertEqual(cost.amount, Decimal('2500000'))
        self.assertEqual(cost.admin, self.admin_ancol)

    def test_phase10_03_operation_create_auto_location(self):
        """F-32: Admin biasa has location auto-forced."""
        img = create_test_image('nota2.jpg')
        resp = self.admin_ancol_client.post(reverse('operation_add'), {
            'kost_location': self.loc_kana.pk,  # Try Kana (wrong)
            'category': 'PAM',
            'amount': '800000',
            'incurred_date': date.today().isoformat(),
            'description': 'Tagihan PAM',
            'proof_file': img,
        })
        if resp.status_code == 302:
            cost = OperationCost.objects.filter(category='PAM').first()
            if cost:
                # Location should be forced to Ancol
                self.assertEqual(cost.kost_location, self.loc_ancol)

    def test_phase10_04_operation_update(self):
        """F-33: Admin edits operational cost."""
        cost = OperationCost.objects.create(
            kost_location=self.loc_ancol, admin=self.admin_ancol,
            category='INTERNET', amount=Decimal('350000'),
            description='Wifi', incurred_date=date.today(),
            proof_file='operation_costs/test.jpg'
        )
        img = create_test_image('nota_edit.jpg')
        resp = self.admin_ancol_client.post(
            reverse('operation_edit', args=[cost.pk]),
            {
                'kost_location': self.loc_ancol.pk,
                'category': 'INTERNET',
                'amount': '400000',
                'incurred_date': date.today().isoformat(),
                'description': 'Wifi upgraded',
                'proof_file': img,
            }
        )
        self.assertEqual(resp.status_code, 302)
        cost.refresh_from_db()
        self.assertEqual(cost.amount, Decimal('400000'))

    def test_phase10_05_operation_delete(self):
        """F-34: Admin deletes operational cost."""
        cost = OperationCost.objects.create(
            kost_location=self.loc_ancol, admin=self.admin_ancol,
            category='LAINNYA', amount=Decimal('50000'),
            description='Delete me', incurred_date=date.today(),
            proof_file='operation_costs/test.jpg'
        )
        resp = self.admin_ancol_client.post(
            reverse('operation_delete', args=[cost.pk])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(OperationCost.objects.filter(pk=cost.pk).exists())

    def test_phase10_06_operation_cross_location_hidden(self):
        """F-31 Security: Admin cannot see costs from other location."""
        OperationCost.objects.create(
            kost_location=self.loc_kana, admin=self.admin_kana,
            category='LISTRIK', amount=Decimal('1000000'),
            description='Kana cost', incurred_date=date.today(),
            proof_file='operation_costs/test.jpg'
        )
        resp = self.admin_ancol_client.get(reverse('operation_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'Kana cost')

    def test_phase10_07_operation_total_expenses_uses_all_recorded_data(self):
        """Operational total card sums all recorded expenses, not only current month."""
        OperationCost.objects.create(
            kost_location=self.loc_ancol,
            admin=self.admin_ancol,
            category='LISTRIK',
            amount=Decimal('100000'),
            description='Biaya bulan ini',
            incurred_date=date.today(),
            proof_file='operation_costs/test1.jpg'
        )
        OperationCost.objects.create(
            kost_location=self.loc_ancol,
            admin=self.admin_ancol,
            category='PAM',
            amount=Decimal('250000'),
            description='Biaya bulan lalu',
            incurred_date=date.today() - timedelta(days=40),
            proof_file='operation_costs/test2.jpg'
        )

        resp = self.admin_ancol_client.get(reverse('operation_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_expenses'], Decimal('350000'))

    # ================================================================
    # PHASE 11: FINANCIAL REPORTING
    # ================================================================
    def test_phase11_01_finance_report_page(self):
        """F-37: Finance report dashboard renders."""
        resp = self.admin_ancol_client.get(reverse('finance_report'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'finance/report_dashboard.html')

    def test_phase11_02_finance_report_filter_year(self):
        """F-37: Filter report by year."""
        resp = self.admin_ancol_client.get(
            reverse('finance_report') + f'?year={date.today().year}'
        )
        self.assertEqual(resp.status_code, 200)

    def test_phase11_03_finance_report_superuser_filter_location(self):
        """F-37: Superuser filters report by location."""
        resp = self.superuser_client.get(
            reverse('finance_report') + f'?year={date.today().year}&kost_location={self.loc_ancol.pk}'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Kost Ancol')

    def test_phase11_04_export_excel(self):
        """F-38: Export Excel downloads .xlsx with 3 sheets."""
        resp = self.admin_ancol_client.get(
            reverse('export_finance_excel') + f'?year={date.today().year}'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        self.assertIn('Laporan_Keuangan', resp['Content-Disposition'])
        # Verify 3 sheets
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(resp.content))
        self.assertEqual(len(wb.sheetnames), 3)
        self.assertIn('Ringkasan Bulanan', wb.sheetnames)
        self.assertIn('Rincian Pemasukan', wb.sheetnames)
        self.assertIn('Rincian Operasional', wb.sheetnames)

    # ================================================================
    # PHASE 12: TENANT CHECKOUT & CLEANUP
    # ================================================================
    def test_phase12_01_checkout_with_unpaid_fails(self):
        """F-23 + B2: Checkout rejected when unpaid invoices exist."""
        tenant = Tenant.objects.create(
            full_name='Checkout Fail', phone_number='081',
            emergency_contact_phone='082'
        )
        contract = TenantContract.objects.create(
            tenant=tenant, room=self.rooms['A-101'],
            start_date=date.today(), monthly_rent_amount=Decimal('1500000')
        )
        Invoice.objects.create(
            contract=contract, billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal('1500000'), electricity_bill_amount=0,
            total_amount=Decimal('1500000'), status='BELUM_LUNAS'
        )
        resp = self.admin_ancol_client.post(
            reverse('tenant_checkout', args=[tenant.pk])
        )
        self.assertEqual(resp.status_code, 302)
        contract.refresh_from_db()
        self.assertTrue(contract.is_active)  # Not checked out

    def test_phase12_02_checkout_success(self):
        """F-23 + B2: Checkout succeeds when all invoices are LUNAS."""
        tenant = Tenant.objects.create(
            full_name='Checkout OK', phone_number='081',
            emergency_contact_phone='082'
        )
        contract = TenantContract.objects.create(
            tenant=tenant, room=self.rooms['A-102'],
            start_date=date.today() - timedelta(days=30),
            monthly_rent_amount=Decimal('2000000')
        )
        Invoice.objects.create(
            contract=contract, billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal('2000000'), electricity_bill_amount=0,
            total_amount=Decimal('2000000'), status='LUNAS'
        )
        resp = self.admin_ancol_client.post(
            reverse('tenant_checkout', args=[tenant.pk])
        )
        self.assertEqual(resp.status_code, 302)
        contract.refresh_from_db()
        self.assertFalse(contract.is_active)
        self.assertIsNotNone(contract.end_date)

    def test_phase12_03_room_becomes_available_after_checkout(self):
        """F-15: Room shows as empty after checkout."""
        tenant = Tenant.objects.create(
            full_name='Room Check', phone_number='081',
            emergency_contact_phone='082'
        )
        room = self.rooms['A-103']
        contract = TenantContract.objects.create(
            tenant=tenant, room=room,
            start_date=date.today(), monthly_rent_amount=Decimal('1500000')
        )
        # Checkout (no invoices → direct checkout)
        self.admin_ancol_client.post(
            reverse('tenant_checkout', args=[tenant.pk])
        )
        # Check room list
        resp = self.admin_ancol_client.get(reverse('room_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Kosong')

    def test_phase12_04_delete_tenant_with_active_contract_fails(self):
        """F-24: Cannot delete tenant with active contract."""
        tenant = Tenant.objects.create(
            full_name='No Delete', phone_number='081',
            emergency_contact_phone='082'
        )
        TenantContract.objects.create(
            tenant=tenant, room=self.rooms['A-101'],
            start_date=date.today(), monthly_rent_amount=Decimal('1500000')
        )
        resp = self.admin_ancol_client.post(
            reverse('tenant_delete', args=[tenant.pk])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Tenant.objects.filter(pk=tenant.pk).exists())

    def test_phase12_05_delete_tenant_success(self):
        """F-24: Delete tenant after checkout (no active contract, no unpaid)."""
        tenant = Tenant.objects.create(
            full_name='Delete Me', phone_number='081',
            emergency_contact_phone='082'
        )
        contract = TenantContract.objects.create(
            tenant=tenant, room=self.rooms['A-103'],
            start_date=date.today() - timedelta(days=30),
            monthly_rent_amount=Decimal('1500000'),
            is_active=False
        )
        contract.end_date = date.today()
        contract.save()

        resp = self.superuser_client.post(
            reverse('tenant_delete', args=[tenant.pk])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Tenant.objects.filter(pk=tenant.pk).exists())

    # ================================================================
    # PHASE 13: SECURITY & EDGE CASES
    # ================================================================
    def test_phase13_01_unauthenticated_dashboard(self):
        """Security: Unauthenticated user redirected from dashboard."""
        c = Client()
        resp = c.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url)

    def test_phase13_02_unauthenticated_invoice_list(self):
        """Security: Unauthenticated user redirected from invoice list."""
        c = Client()
        resp = c.get(reverse('invoice_list'))
        self.assertEqual(resp.status_code, 302)

    def test_phase13_03_admin_ancol_cannot_see_kana_tenants(self):
        """Security: Admin Ancol cannot see Kana tenants."""
        tenant = Tenant.objects.create(
            full_name='Kana Only Person', phone_number='081',
            emergency_contact_phone='082'
        )
        TenantContract.objects.create(
            tenant=tenant, room=self.rooms['K-101'],
            start_date=date.today(), monthly_rent_amount=Decimal('1500000')
        )
        resp = self.admin_ancol_client.get(reverse('tenant_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'Kana Only Person')

    def test_phase13_04_admin_ancol_cannot_see_kana_invoices(self):
        """Security: Admin Ancol cannot see Kana invoices."""
        tenant = Tenant.objects.create(
            full_name='Hidden Tenant', phone_number='081',
            emergency_contact_phone='082'
        )
        contract = TenantContract.objects.create(
            tenant=tenant, room=self.rooms['K-102'],
            start_date=date.today(), monthly_rent_amount=Decimal('1800000')
        )
        Invoice.objects.create(
            contract=contract, billing_period_start=date.today(),
            due_date=date.today() + timedelta(days=10),
            base_rent_amount=Decimal('1800000'), electricity_bill_amount=0,
            total_amount=Decimal('1800000'), status='BELUM_LUNAS'
        )
        resp = self.admin_ancol_client.get(reverse('invoice_list'))
        self.assertNotContains(resp, 'Hidden Tenant')

    def test_phase13_05_checkout_cross_location_forbidden(self):
        """Security: Admin Ancol cannot checkout Kana tenant."""
        tenant = Tenant.objects.create(
            full_name='Cross Checkout', phone_number='081',
            emergency_contact_phone='082'
        )
        contract = TenantContract.objects.create(
            tenant=tenant, room=self.rooms['K-103'],
            start_date=date.today(), monthly_rent_amount=Decimal('1500000')
        )
        resp = self.admin_ancol_client.post(
            reverse('tenant_checkout', args=[tenant.pk])
        )
        contract.refresh_from_db()
        self.assertTrue(contract.is_active)  # Not changed

    def test_phase13_06_superuser_sees_all_invoices(self):
        """Security: Superuser sees invoices from all locations."""
        for room_key, loc in [('A-101', self.loc_ancol), ('K-101', self.loc_kana)]:
            tenant = Tenant.objects.create(
                full_name=f'Global {room_key}', phone_number='081',
                emergency_contact_phone='082'
            )
            contract = TenantContract.objects.create(
                tenant=tenant, room=self.rooms[room_key],
                start_date=date.today(), monthly_rent_amount=Decimal('1500000')
            )
            Invoice.objects.create(
                contract=contract, billing_period_start=date.today(),
                due_date=date.today() + timedelta(days=10),
                base_rent_amount=Decimal('1500000'), electricity_bill_amount=0,
                total_amount=Decimal('1500000'), status='BELUM_LUNAS'
            )
        resp = self.superuser_client.get(reverse('invoice_list'))
        self.assertContains(resp, 'Global A-101')
        self.assertContains(resp, 'Global K-101')

    def test_phase13_07_checkout_requires_post(self):
        """Security: Checkout only accepts POST (C-01 fix)."""
        tenant = Tenant.objects.create(
            full_name='GET Checkout', phone_number='081',
            emergency_contact_phone='082'
        )
        TenantContract.objects.create(
            tenant=tenant, room=self.rooms['A-101'],
            start_date=date.today(), monthly_rent_amount=Decimal('1500000')
        )
        resp = self.admin_ancol_client.get(
            reverse('tenant_checkout', args=[tenant.pk])
        )
        self.assertEqual(resp.status_code, 405)  # Method Not Allowed

    def test_phase13_08_room_delete_requires_post(self):
        """Security: Room delete only accepts POST."""
        room = Room.objects.create(
            kost_location=self.loc_ancol, room_number='A-DEL',
            price_monthly=Decimal('1000000'), capacity=1
        )
        resp = self.admin_ancol_client.get(
            reverse('room_delete', args=[room.pk])
        )
        self.assertEqual(resp.status_code, 405)

    def test_phase13_09_operation_delete_requires_post(self):
        """Security: Operation delete only accepts POST."""
        cost = OperationCost.objects.create(
            kost_location=self.loc_ancol, admin=self.admin_ancol,
            category='LAINNYA', amount=Decimal('1000'),
            description='Del test', incurred_date=date.today(),
            proof_file='operation_costs/test.jpg'
        )
        resp = self.admin_ancol_client.get(
            reverse('operation_delete', args=[cost.pk])
        )
        self.assertEqual(resp.status_code, 405)

    def test_phase13_10_verify_requires_post(self):
        """Security: Verify payment only accepts POST."""
        tenant, contract, invoice, payment = self._setup_verification_data()
        resp = self.admin_ancol_client.get(
            reverse('verify_payment', args=[payment.pk, 'approve'])
        )
        self.assertEqual(resp.status_code, 405)

    def test_phase13_11_plain_user_cannot_create_tenant(self):
        """Security: Non-staff user must not create tenant records."""
        resp = self.plain_user_client.post(reverse('tenant_add'), {
            'full_name': 'Unauthorized Tenant',
            'phone_number': '0812345',
            'emergency_contact_phone': '0899999',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Tenant.objects.filter(full_name='Unauthorized Tenant').exists())

    def test_phase13_12_plain_user_cannot_create_room(self):
        """Security: Non-staff user must not create room records."""
        resp = self.plain_user_client.post(reverse('room_add'), {
            'kost_location': self.loc_ancol.pk,
            'room_number': 'X-999',
            'price_monthly': '1200000',
            'is_token_electricity': False,
            'capacity': 1,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Room.objects.filter(room_number='X-999').exists())

    def test_phase13_13_plain_user_cannot_assign_room(self):
        """Security: Non-staff user must not assign tenant to room."""
        tenant = Tenant.objects.create(
            full_name='Unauthorized Assign Tenant',
            phone_number='081111',
            emergency_contact_phone='082222'
        )
        resp = self.plain_user_client.post(
            reverse('tenant_assign_room', args=[tenant.pk]),
            {
                'room': self.rooms['A-101'].pk,
                'start_date': date.today().isoformat(),
                'monthly_rent_amount': '1500000',
            }
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(TenantContract.objects.filter(tenant=tenant, is_active=True).exists())

    def test_phase13_14_prevent_double_active_contract_same_room(self):
        """Data integrity: A room cannot have more than one active contract."""
        tenant1 = Tenant.objects.create(
            full_name='Integrity Tenant 1',
            phone_number='081333',
            emergency_contact_phone='082333'
        )
        tenant2 = Tenant.objects.create(
            full_name='Integrity Tenant 2',
            phone_number='081444',
            emergency_contact_phone='082444'
        )

        TenantContract.objects.create(
            tenant=tenant1,
            room=self.rooms['A-103'],
            start_date=date.today(),
            monthly_rent_amount=Decimal('1500000'),
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            TenantContract.objects.create(
                tenant=tenant2,
                room=self.rooms['A-103'],
                start_date=date.today(),
                monthly_rent_amount=Decimal('1500000'),
                is_active=True,
            )

    # ================================================================
    # PHASE 14: MANAGEMENT COMMANDS
    # ================================================================
    def test_phase14_01_seed_data_command(self):
        """F-42: seed_data command runs without errors."""
        # Note: This creates its own data; just test it doesn't crash
        call_command('seed_data')
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
        self.admin_ancol_client.post(reverse('tenant_add'), {
            'full_name': 'Lifecycle Tenant',
            'phone_number': '081111222333',
            'emergency_contact_phone': '089999888777',
        })
        tenant = Tenant.objects.get(full_name='Lifecycle Tenant')

        # 2. Assign Room A-101
        self.admin_ancol_client.post(
            reverse('tenant_assign_room', args=[tenant.pk]),
            {
                'room': self.rooms['A-101'].pk,
                'start_date': (date.today() - timedelta(days=5)).isoformat(),
                'monthly_rent_amount': '1500000',
            }
        )
        contract = TenantContract.objects.get(tenant=tenant, is_active=True)
        pin = contract.payment_pin
        self.assertEqual(len(pin), 6)

        # 3. Generate Invoice
        self.admin_ancol_client.post(reverse('invoice_generate_bulk'))
        invoice = Invoice.objects.filter(contract=contract).first()
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.status, 'BELUM_LUNAS')

        # 4. Input Electricity (Ancol = meteran)
        self.admin_ancol_client.post(
            reverse('invoice_detail', args=[invoice.pk]),
            {
                'meter_reading_start': 500,
                'meter_reading_end': 600,
                'rate_per_kwh': '1500.00',
            }
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.electricity_bill_amount, Decimal('150000.00'))
        self.assertEqual(invoice.total_amount, Decimal('1650000.00'))

        # 5. Tenant logs in via PIN portal
        lifecycle_client = Client()
        resp = lifecycle_client.post(reverse('public_payment_step1'), {
            'kost_location': self.loc_ancol.pk,
            'room_number': 'A-101',
            'pin': pin,
        })
        self.assertEqual(resp.status_code, 302)

        # 6. Tenant uploads payment proof
        img = create_test_image()
        resp = lifecycle_client.post(
            reverse('public_payment_step2'),
            {'payment_proof_file': img},
            format='multipart'
        )
        self.assertEqual(resp.status_code, 200)  # success.html
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'MENUNGGU_VERIFIKASI')

        # 7. Admin approves payment
        payment = Payment.objects.filter(invoice=invoice).first()
        self.assertIsNotNone(payment)
        self.admin_ancol_client.post(
            reverse('verify_payment', args=[payment.pk, 'approve'])
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'LUNAS')

        # 8. Print receipt
        resp = self.admin_ancol_client.get(
            reverse('print_receipt', args=[invoice.pk])
        )
        self.assertEqual(resp.status_code, 200)

        # 9. Checkout
        resp = self.admin_ancol_client.post(
            reverse('tenant_checkout', args=[tenant.pk])
        )
        self.assertEqual(resp.status_code, 302)
        contract.refresh_from_db()
        self.assertFalse(contract.is_active)
        self.assertEqual(contract.end_date, date.today())

        # 10. Delete tenant
        resp = self.superuser_client.post(
            reverse('tenant_delete', args=[tenant.pk])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Tenant.objects.filter(pk=tenant.pk).exists())
