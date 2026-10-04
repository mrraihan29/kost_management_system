# LAPORAN DEEP ANALYSIS — EVY KOST MANAGEMENT SYSTEM
## Deep Code Quality, Bug Detection & Business Process Gap Analysis

> **Tanggal:** 26 Juni 2025  
> **Versi Kode:** Commit `319c708` (post-security audit)  
> **Cakupan:** Seluruh 47 fitur, 4 apps, 18+ source files  
> **Metode:** Manual static analysis + cross-reference dengan BUSINESS_PROCESS_SIMULATION.md  

---

## DAFTAR ISI

1. [Ringkasan Eksekutif](#1-ringkasan-eksekutif)
2. [KATEGORI A — Critical Bugs (HARUS Diperbaiki)](#2-kategori-a--critical-bugs)
3. [KATEGORI B — Code Quality & Efficiency](#3-kategori-b--code-quality--efficiency)
4. [KATEGORI C — Business Process Gaps](#4-kategori-c--business-process-gaps)
5. [Matriks Prioritas](#5-matriks-prioritas)
6. [Status Perbaikan](#6-status-perbaikan)

---

## 1. RINGKASAN EKSEKUTIF

| Kategori | Jumlah Temuan | Kritis | Harus Diperbaiki | Saran |
|----------|:------------:|:------:|:-----------------:|:-----:|
| **A. Critical Bugs** | 7 | 7 | — | — |
| **B. Code Quality** | 10 | — | 6 | 4 |
| **C. Business Process Gaps** | 8 | — | 3 | 5 |
| **TOTAL** | **25** | **7** | **9** | **9** |

---

## 2. KATEGORI A — CRITICAL BUGS

### A-01: Duplikasi Invoice pada `generate_invoices_bulk` (KRITIS)

**File:** `finance/views.py` → `generate_invoices_bulk()`  
**Masalah:**  
View menggunakan pengecekan **exact date match** untuk mencegah duplikasi:
```python
exists = Invoice.objects.filter(
    contract=contract,
    billing_period_start=billing_start  # ← exact date
).exists()
```
Sedangkan management command `generate_monthly_invoices` menggunakan **month/year match**:
```python
exists = Invoice.objects.filter(
    contract=contract,
    billing_period_start__month=billing_start.month,
    billing_period_start__year=billing_start.year
).exists()
```

**Dampak:**  
Jika `contract.start_date.day` berubah (edit kontrak) antara eksekusi command dan view, invoice bisa terbuat DUPLIKAT untuk bulan yang sama karena tanggal billing_start berbeda (misal 15 Maret vs 20 Maret).

**Solusi:** Ubah view agar menggunakan month/year match yang sama.

---

### A-02: `tenant_delete` Tanpa Validasi Lokasi (KRITIS)

**File:** `tenants/views.py` → `tenant_delete()`  
**Masalah:**  
View mengecek active contracts dan unpaid invoices, tapi TIDAK mengecek apakah admin yang login memiliki akses ke lokasi tenant tersebut.

```python
@require_POST
@login_required
def tenant_delete(request, pk):
    tenant = get_object_or_404(Tenant, pk=pk)
    # ← TIDAK ADA cek lokasi!
    # Admin lokasi A bisa menghapus tenant lokasi B via URL manipulation
```

**Dampak:**  
Admin dari lokasi A bisa menghapus data tenant di lokasi B dengan mengirim POST ke `/staff/tenants/{pk}/delete/`. Melanggar Business Rule B5.

**Solusi:** Tambahkan validasi lokasi sebelum operasi delete.

---

### A-03: State Machine Maintenance Ticket Tidak Ditegakkan (KRITIS)

**File:** `finance/views.py` → `admin_ticket_update()`  
**Masalah:**  
View menerima SEMUA status valid tanpa mengecek transisi:
```python
valid_statuses = dict(MaintenanceTicket.STATUS_CHOICES)
if new_status and new_status in valid_statuses:
    ticket.status = new_status  # ← skip ANY transition
```

**State diagram yang SEHARUSNYA ditegakkan (dari BUSINESS_PROCESS_SIMULATION.md):**
- PENDING → PROSES, DITOLAK
- PROSES → SELESAI, PENDING (rollback)
- SELESAI → final (tidak bisa diubah)
- DITOLAK → final (tidak bisa diubah)

**Dampak:**  
- Admin bisa langsung set PENDING → SELESAI (skip PROSES)
- Admin bisa reopen tiket SELESAI atau DITOLAK (final states)
- Melanggar state diagram di Business Process

**Solusi:** Implementasi `VALID_TRANSITIONS` dict dan validasi sebelum update.

---

### A-04: Label "Wajib" pada Photo Maintenance Tapi Field Opsional

**File:** `finance/forms.py` → `MaintenanceForm`, `tenants/models.py` → `MaintenanceTicket`  
**Masalah:**  
```python
# FORM: Label mengatakan "Wajib"
labels = {'photo': 'Foto Kerusakan (Wajib)'}

# MODEL: Field opsional
photo = models.ImageField(..., blank=True, null=True)

# CLEAN: Tidak memaksa ada file
def clean_photo(self):
    f = self.cleaned_data.get('photo')
    if f:
        validate_image_file(f)
    return f  # ← return None jika tidak upload = OK
```

**Dampak:** User diminta upload foto "wajib" tapi bisa submit tanpa foto. Menyesatkan.

**Solusi:** Pilih salah satu: ubah label menjadi "(Opsional)" atau tambahkan validasi `required`.

---

### A-05: `operation_list` Total Menampilkan All-Time Bukan Bulan Ini

**File:** `finance/views.py` → `operation_list()`  
**Masalah:**  
```python
costs = OperationCost.objects.select_related(...).order_by('-incurred_date')
# ← Tidak ada filter bulan!
total_expenses = costs.aggregate(Sum('amount'))['amount__sum'] or 0
```

**Business Process (Fase 8, Step 8.1):** "*Navigasi ke Operasional: List pengeluaran + total bulan ini*"  
**Dampak:** Total menunjukkan akumulasi SELURUH pengeluaran dari awal waktu, bukan bulan berjalan.

**Solusi:** Pisahkan query: satu untuk list (all-time + pagination), satu untuk KPI (bulan ini).

---

### A-06: `income_this_month` Menggunakan Billing Period Bukan Tanggal Pembayaran

**File:** `core/views.py` → `admin_dashboard()`  
**Masalah:**  
```python
income_this_month = invoices.filter(
    status='LUNAS',
    billing_period_start__month=now.month,  # ← billing period, bukan waktu bayar
    billing_period_start__year=now.year
).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
```

**Dampak:**  
- Invoice billing Januari yang dibayar di Februari → TIDAK terhitung sebagai pemasukan Februari
- Invoice billing Februari yang dibayar di Januari (bayar muka) → TERHITUNG sebagai pemasukan Februari, padahal uang sudah masuk Januari
- KPI "Pemasukan Bulan Ini" tidak mencerminkan arus kas aktual

**Solusi:** Gunakan `payment.verified_at__month/year` sebagai filter, bukan `billing_period_start`.

---

### A-07: Room `capacity` Tidak Pernah Digunakan

**File:** `core/models.py` → `Room.capacity`, `tenants/models.py` → constraint  
**Masalah:**  
Field `capacity = models.IntegerField(default=1)` ada di model Room, tapi:
- Constraint `uniq_active_contract_per_room` selalu membatasi 1 kontrak aktif per kamar
- Tidak ada logika yang membatasi berdasarkan `capacity`
- Kamar dengan `capacity=2` tetap hanya bisa diisi 1 penghuni

**Dampak:** Field `capacity` tidak berfungsi, menyesatkan.

**Solusi:** Hapus field jika memang 1 kamar = 1 kontrak, ATAU implementasi logika capacity-based assignment.

---

## 3. KATEGORI B — CODE QUALITY & EFFICIENCY

### B-01: Pola Cek Lokasi Diulang 15+ Kali (DRY Violation) ⚠️

**Files:** Hampir semua view di `core/views.py`, `finance/views.py`, `tenants/views.py`  
**Masalah:**  
Pola berikut copy-paste di setiap view function:
```python
if not request.user.is_superuser:
    if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
        user_location = request.user.admin_profile.assigned_location
        queryset = queryset.filter(...)
    else:
        queryset = queryset.none()
```

**Dampak:** Jika ada perubahan logika akses (misal tambah role baru), harus edit 15+ tempat.

**Solusi:** Buat decorator `@location_required` dan helper `get_user_location(user)`.

---

### B-02: N+1 Query di `room_list` ⚠️

**File:** `core/views.py` → `room_list()`  
**Masalah:**  
```python
rooms = list(rooms)  # Evaluate queryset, contracts NOT prefetched
# ...
for room in rooms:
    room.active_contract = room.contracts.filter(is_active=True).select_related('tenant').first()
    # ← 1 query PER ROOM! Dengan 68 kamar = 68 extra queries
```

**Dampak:** Pada kost dengan 68 kamar, ini menghasilkan 69 queries (1 + 68 N+1).

**Solusi:** Gunakan `Prefetch` pada queryset awal.

---

### B-03: `sync_overdue_invoice_statuses()` Dipanggil Setiap GET

**Files:** `core/views.py` → `admin_dashboard()`, `finance/views.py` → `invoice_list()`  
**Masalah:**  
```python
@login_required
def admin_dashboard(request):
    sync_overdue_invoice_statuses()  # ← UPDATE query setiap kali dashboard dibuka
```

**Dampak:** Setiap admin buka dashboard = 1 UPDATE query ke semua invoice. Dengan 3 admin refresh 10x/hari = 30 unnecessary write queries/hari.

**Solusi:** Pindahkan ke cron/celery task, atau cache hasilnya.

---

### B-04: `LocMemCache` Tidak Cocok untuk Production Multi-Worker

**File:** `config/settings.py`  
**Masalah:**  
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
```

**Dampak:**  
- Rate limiting (SEC-01) menggunakan cache ini
- `LocMemCache` per-process, tidak shared antar Gunicorn workers
- Attacker bisa bypass rate limit dengan mengirim request ke worker berbeda

**Solusi:** Gunakan `django.core.cache.backends.db.DatabaseCache` atau Redis di production.

---

### B-05: `TenantContractForm` Room Filter Tidak Berlaku untuk Superuser

**File:** `tenants/forms.py` → `TenantContractForm.__init__()`  
**Masalah:**  
```python
if user and not user.is_superuser:
    # Filter rooms: hanya vacant + lokasi admin
else:
    # ← Superuser: room queryset TIDAK di-filter
    # Akan menampilkan SEMUA room, termasuk yang SUDAH TERISI
```

**Dampak:** Superuser bisa melihat dan memilih kamar yang sudah terisi saat assign room.

**Solusi:** Selalu exclude occupied rooms, hanya location filter yang opsional untuk superuser.

---

### B-06: `public_logout` Menerima GET Request

**File:** `finance/views.py` → `public_logout()`  
**Masalah:**  
```python
def public_logout(request):  # ← Accepts GET
    if 'verified_contract_id' in request.session:
        del request.session['verified_contract_id']
```

**Dampak:**  
Rentan CSRF logout: `<img src="/bayar/keluar/">` di halaman lain bisa memaksa tenant logout.

**Solusi:** Tambahkan `@require_POST`.

---

### B-07: Missing `db_index` pada Field yang Sering Difilter

**Files:** `finance/models.py`, `tenants/models.py`  
**Fields tanpa index yang sering difilter:**
- `Invoice.status` — difilter di 5+ queries
- `Invoice.billing_period_start` — difilter di 4+ queries
- `Invoice.due_date` — difilter di overdue queries
- `TenantContract.is_active` — difilter di 8+ queries
- `OperationCost.incurred_date` — difilter di report queries

**Dampak:** Query performance degradasi seiring pertumbuhan data.

---

### B-08: Race Condition di `generate_unique_pin`

**File:** `tenants/models.py` → `TenantContract.generate_unique_pin()`  
**Masalah:**  
```python
def generate_unique_pin(self):
    while True:
        new_pin = ''.join(random.choices(string.digits, k=6))
        if not TenantContract.objects.filter(payment_pin=new_pin).exists():
            return new_pin
            # ← Between check and save, another thread could claim this PIN
```

**Dampak:** IntegrityError crash jika dua kontrak dibuat bersamaan dan mendapat PIN yang sama.

**Solusi:** Wrap save() dalam try/except IntegrityError dengan retry.

---

### B-09: `finance/views.py` Terlalu Besar (20+ Views, 400+ Baris)

**File:** `finance/views.py`  
**Masalah:** File berisi 20+ view functions mencakup public payment, admin invoice, operations, maintenance, reporting, dan Excel export. Melanggar Single Responsibility Principle.

**Solusi:** Split menjadi `views/payment.py`, `views/invoice.py`, `views/operation.py`, `views/maintenance.py`, `views/reporting.py`.

---

### B-10: Inconsistent Auth Pattern (CBV Mixin vs FBV Inline Check)

**Files:** `tenants/views.py` (CBV), semua views lain (FBV)  
**Masalah:** Tenant views menggunakan CBV dengan `StaffWithLocationRequiredMixin`, tapi semua view lain menggunakan manual inline checks. Tidak konsisten.

**Solusi:** Buat decorator `@staff_with_location_required` untuk FBVs, atau migrasikan ke CBV.

---

## 4. KATEGORI C — BUSINESS PROCESS GAPS

### C-01: Tidak Ada `billing_period_end` pada Invoice

**Model:** `finance/models.py` → `Invoice`  
**Gap:** Hanya ada `billing_period_start`, tidak ada `billing_period_end`.
- Tidak bisa menentukan periode invoice (1 bulan? 2 minggu?)
- Tidak bisa mencegah overlap invoices untuk periode yang sama
- Display hanya menunjukkan "Periode: Februari 2026" tanpa end date

---

### C-02: Tidak Ada UI untuk Membuat Lokasi Baru

**Gap:** F-13 (`location_list`) dan F-14 (`location_update`) ada, tapi tidak ada `location_create`.
- Jika bisnis expand ke lokasi baru, harus via Django Admin Panel
- Owner (non-technical) mungkin kesulitan

---

### C-03: Tidak Ada UI untuk Hapus Staff

**Gap:** F-39 (List), F-40 (Create), F-41 (Update) ada, tapi tidak ada Staff Delete.
- Admin yang resign tidak bisa dihapus dari UI
- Hanya bisa di-deactivate (`is_active=False`) via Edit

---

### C-04: Invoice Hanya Bisa Digenerate untuk "Bulan Depan"

**Gap:** `generate_invoices_bulk` selalu menghitung `next_month = today + 1 month`.
- Tidak bisa generate invoice bulan berjalan (untuk tenant baru mid-month)
- Tidak bisa generate invoice bulan lalu (jika terlewat)
- Tidak ada pro-rata calculation untuk partial month

---

### C-05: Tidak Ada Notifikasi ke Tenant

**Gap:** Tidak ada mekanisme notifikasi ketika:
- Pembayaran disetujui/ditolak
- Status maintenance ticket berubah
- Invoice baru ter-generate
- Tagihan mendekati/melewati jatuh tempo

Tenant harus login manual untuk cek status.

---

### C-06: Tidak Bisa Membatalkan Checkout (Undo)

**Gap:** Setelah `tenant_checkout()`, kontrak di-set `is_active=False` dan `end_date=today`.
- Jika checkout salah tekan, tidak ada cara untuk membatalkan
- Admin harus buat kontrak baru dengan PIN baru

---

### C-07: Payment History dalam Invoice Detail Tidak Lengkap

**Gap:** `invoice_detail.html` hanya menampilkan `invoice.payments.last` (bukti terakhir).
- Jika ada payment yang ditolak lalu di-upload ulang, history payment sebelumnya tidak terlihat
- Admin tidak bisa melihat rejection notes dari payment sebelumnya

---

### C-08: Tidak Ada Pencatatan Tanggal Invoice Diverifikasi di Dashboard

**Gap:** Dashboard attention list menampilkan invoice yang perlu perhatian, tapi setelah approved:
- Tidak ada "recently approved" section
- Tidak ada activity log yang visible di UI
- Admin tidak bisa melihat apa yang sudah di-approve hari ini

---

## 5. MATRIKS PRIORITAS

| ID | Severity | Effort | Impact | Bisa Difix? |
|----|----------|--------|--------|:-----------:|
| A-01 | 🔴 Critical | Low | Duplikasi data keuangan | ✅ |
| A-02 | 🔴 Critical | Low | Security breach (B5) | ✅ |
| A-03 | 🔴 Critical | Medium | Data integrity | ✅ |
| A-04 | 🟠 High | Low | UX mismatch | ✅ |
| A-05 | 🟠 High | Low | KPI salah | ✅ |
| A-06 | 🟠 High | Medium | KPI salah | ✅ |
| A-07 | 🟡 Medium | Low | Dead code | ✅ |
| B-01 | 🟡 Medium | Medium | Maintainability | ✅ |
| B-02 | 🟡 Medium | Low | Performance | ✅ |
| B-03 | 🟡 Medium | Low | Performance | ✅ |
| B-04 | 🟡 Medium | Low | Security bypass | ✅ |
| B-05 | 🟡 Medium | Low | Data integrity | ✅ |
| B-06 | 🟢 Low | Low | Minor security | ✅ |
| B-07 | 🟢 Low | Low | Future performance | ✅ |
| B-08 | 🟢 Low | Low | Race condition | ✅ |
| B-09 | 🟢 Low | High | Maintainability | 🔄 |
| B-10 | 🟢 Low | High | Consistency | 🔄 |
| C-01 | 🟡 Medium | Medium | Data model | 🔄 |
| C-02 | 🟢 Low | Low | Missing feature | ✅ |
| C-03 | 🟢 Low | Low | Missing feature | ✅ |
| C-04 | 🟡 Medium | Medium | Business limitation | 🔄 |
| C-05 | 🟡 Medium | High | UX gap | 🔄 |
| C-06 | 🟢 Low | Low | UX gap | 🔄 |
| C-07 | 🟢 Low | Low | UX gap | ✅ |
| C-08 | 🟢 Low | Medium | UX gap | 🔄 |

✅ = Akan diperbaiki  |  🔄 = Saran (perlu diskusi/future sprint)

---

## 6. STATUS PERBAIKAN

| ID | Status | Commit |
|----|--------|--------|
| A-01 | ✅ Fixed | — |
| A-02 | ✅ Fixed | — |
| A-03 | ✅ Fixed | — |
| A-04 | ✅ Fixed | — |
| A-05 | ✅ Fixed | — |
| A-06 | ✅ Fixed | — |
| A-07 | ✅ Fixed | — |
| B-01 | ✅ Fixed | — |
| B-02 | ✅ Fixed | — |
| B-03 | ✅ Fixed | — |
| B-04 | ✅ Fixed | — |
| B-05 | ✅ Fixed | — |
| B-06 | ✅ Fixed | — |
| B-07 | ✅ Fixed | — |
| B-08 | ✅ Fixed | — |
| B-09 | 🔄 Saran | — |
| B-10 | 🔄 Saran | — |
| C-01 to C-08 | 🔄 Saran | — |

---

> *Dokumen ini dibuat sebagai hasil deep analysis dan menjadi referensi untuk perbaikan.*
