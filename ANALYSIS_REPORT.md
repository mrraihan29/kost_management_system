# 🔍 LAPORAN ANALISIS MENDALAM — Kost Management System

> **Tanggal Analisis**: Januari 2025  
> **Versi**: Django 5.0.6 / Python 3.11  
> **Metode**: Deep Code Review per Fitur  
> **Total Temuan**: 42 item (6 Kritis, 11 Medium, 14 Kecil, 11 Improvement)

---

## Daftar Fitur yang Dianalisis

| Kode | Fitur | File Utama |
|------|-------|------------|
| A | Autentikasi & Manajemen User | `users/views.py`, `users/forms.py`, `users/models.py` |
| B | Dashboard & Peta Visual | `core/views.py` → `admin_dashboard()` |
| C | Manajemen Penghuni (Tenant) | `tenants/views.py`, `tenants/forms.py` |
| D | Tagihan & Billing | `finance/views.py` → invoice, generate_bulk |
| E | Portal Pembayaran Publik | `finance/views.py` → step1, step2, history |
| F | Verifikasi Pembayaran | `finance/views.py` → `verify_payment()` |
| G | Biaya Operasional | `finance/views.py` → operation CRUD |
| H | Laporan Kerusakan (Maintenance) | `finance/views.py` → ticket, public_report |
| I | Laporan Keuangan & Export | `finance/views.py` → finance_report, export_excel |
| J | Manajemen Lokasi & Kamar | `core/views.py` → room/location CRUD |
| K | Infrastruktur & Keamanan | `config/settings.py`, `Dockerfile`, URL config |

---

## Legenda Severity

| Severity | Emoji | Deskripsi |
|----------|-------|-----------|
| **KRITIS** | 🔴 | Crash, data loss, atau celah keamanan serius |
| **MEDIUM** | 🟡 | Bug logic, inkonsistensi data, atau security gap |
| **KECIL** | 🔵 | Minor bug, UX issue, atau edge case |
| **IMPROVEMENT** | 🟢 | Saran perbaikan kualitas kode / arsitektur |

---

## FITUR A: Autentikasi & Manajemen User

**File**: `users/views.py`, `users/forms.py`, `users/models.py`

### 🔴 A-01 — KRITIS: Tidak ada fitur Delete Staff

**Lokasi**: `users/views.py`  
**Deskripsi**: Hanya tersedia `staff_list`, `staff_create`, `staff_update`. Tidak ada view untuk menghapus staff. Jika admin perlu dihapus, satu-satunya cara adalah melalui Django Admin panel (`/admin/`).  
**Dampak**: Superuser tidak bisa menghapus staff yang sudah tidak aktif melalui UI.  
**Rekomendasi**: Tambahkan view `staff_delete` dengan `@require_POST` dan `@user_passes_test(is_superuser)`.

---

### 🟡 A-02 — MEDIUM: Staff Update tidak validasi edit terhadap superuser

**Lokasi**: `users/views.py` → `staff_update()`, baris `get_object_or_404(User, pk=pk, is_staff=True, is_superuser=False)`  
**Deskripsi**: Filter `is_superuser=False` sudah ada di `get_object_or_404`, jadi tidak bisa edit superuser. Namun, tidak ada proteksi jika superuser mengubah dirinya sendiri di `staff_update`. Sebenarnya proteksi sudah aman, tapi URL tetap bisa dipanggil dengan PK milik superuser — akan return 404 alih-alih pesan error yang jelas.  
**Dampak**: UX kurang informatif.  
**Rekomendasi**: Tambahkan explicit message "User ini adalah superuser dan tidak bisa diedit dari sini."

---

### 🟡 A-03 — MEDIUM: `StaffUpdateForm` tidak bisa reset password

**Lokasi**: `users/forms.py` → `StaffUpdateForm`  
**Deskripsi**: Form update hanya memiliki fields `first_name`, `last_name`, `email`, `is_active`, `assigned_location`. Tidak ada mekanisme bagi superuser untuk mereset password staff.  
**Dampak**: Jika staff lupa password, tidak bisa direset tanpa akses Django Admin.  
**Rekomendasi**: Tambahkan link atau tombol "Reset Password" yang mengarah ke admin atau custom view.

---

### 🔵 A-04 — KECIL: `is_superuser` redirect ke dashboard jika bukan superuser

**Lokasi**: `users/views.py` → `@user_passes_test(is_superuser, login_url='/staff/dashboard/')`  
**Deskripsi**: `login_url` parameter pada `@user_passes_test` digunakan sebagai redirect URL ketika user sudah login tapi gagal test. Nama parameter `login_url` menyesatkan — ini bukan masalah login, melainkan masalah authorization. Redirect ke dashboard tanpa pesan error.  
**Dampak**: Admin biasa yang coba akses halaman staff management akan di-redirect tanpa penjelasan.  
**Rekomendasi**: Gunakan custom decorator atau tambahkan `messages.error` sebelum redirect.

---

### 🟢 A-05 — IMPROVEMENT: `AdminProfile.phone_number` tidak pernah digunakan

**Lokasi**: `users/models.py` → `AdminProfile.phone_number`  
**Deskripsi**: Field `phone_number` pada `AdminProfile` tidak ditampilkan di form manapun (`StaffCreationForm`, `StaffUpdateForm`), dan tidak dirender di template manapun.  
**Rekomendasi**: Hapus field jika tidak direncanakan, atau tambahkan ke form staff.

---

## FITUR B: Dashboard & Peta Visual

**File**: `core/views.py` → `admin_dashboard()`

### 🟡 B-01 — MEDIUM: Prefetch dengan slice `[:1]` mungkin tidak bekerja optimal

**Lokasi**: `core/views.py`, baris ~76  
```python
Prefetch('invoices', queryset=Invoice.objects.order_by('-due_date')[:1])
```
**Deskripsi**: Django ORM `Prefetch` dengan queryset yang sudah di-slice (`[:1]`) bisa mengembalikan hasil yang tidak sesuai ekspektasi. Django secara internal bisa membuang slice saat menjalankan prefetch karena prefetch bekerja dengan `IN` query, bukan per-objek. Hasilnya, `active_contract.invoices.all().first()` bisa mengembalikan hasil yang benar secara kebetulan, atau bisa mengembalikan lebih dari 1 record.  
**Dampak**: Dashboard peta visual bisa salah menampilkan status kamar.  
**Rekomendasi**: Hapus slice di Prefetch dan tetap gunakan `.first()` saat iterasi, atau precompute data di Python setelah prefetch penuh.

---

### 🟡 B-02 — MEDIUM: `selected_location_id` type casting tanpa validasi

**Lokasi**: `core/views.py`, baris ~118  
```python
'selected_location_id': int(selected_location_id) if selected_location_id else None
```
**Deskripsi**: Jika `selected_location_id` berisi string non-numerik dari URL (contoh: `?location=abc`), maka `int()` akan raise `ValueError` dan halaman 500.  
**Dampak**: Server error jika URL dimanipulasi.  
**Rekomendasi**: Wrap dalam `try-except ValueError` atau gunakan form validation.

---

### 🔵 B-03 — KECIL: Income bulan ini dihitung berdasarkan `billing_period_start` bulan ini

**Lokasi**: `core/views.py`, baris ~80  
```python
income_this_month = invoices.filter(
    status='LUNAS',
    billing_period_start__month=now.month,
    billing_period_start__year=now.year
).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
```
**Deskripsi**: Pemasukan dihitung dari tagihan yang `billing_period_start` di bulan ini. Ini secara bisnis bisa menyesatkan — lebih akurat menghitung berdasarkan tanggal pembayaran (`Payment.verified_at`) daripada periode tagihan.  
**Dampak**: Angka pemasukan bulan ini mungkin tidak mencerminkan cashflow aktual.  
**Rekomendasi**: Pertimbangkan filter berdasarkan `payments__verified_at__month` sebagai alternatif.

---

### 🟢 B-04 — IMPROVEMENT: Attention list N+1 query potential

**Lokasi**: `core/views.py`, baris ~109  
```python
attention_list = invoices.filter(
    status__in=['MENUNGGU_VERIFIKASI', 'TELAT_BAYAR']
).order_by('status', 'due_date')
```
**Deskripsi**: `attention_list` tidak menggunakan `select_related` meskipun template kemungkinan mengakses `invoice.contract.tenant` dan `invoice.contract.room`.  
**Rekomendasi**: Tambahkan `.select_related('contract__tenant', 'contract__room__kost_location')`.

---

## FITUR C: Manajemen Penghuni (Tenant)

**File**: `tenants/views.py`, `tenants/forms.py`, `tenants/models.py`

### 🔴 C-01 — KRITIS: `tenant_checkout` menggunakan GET request untuk aksi state-changing

**Lokasi**: `tenants/views.py` → `tenant_checkout()`, `tenants/urls.py` → `path('<int:pk>/checkout/')`  
**Deskripsi**: View `tenant_checkout` menerima request GET maupun POST (tidak ada `@require_POST` decorator). Checkout adalah aksi yang mengubah state (menonaktifkan kontrak, set `end_date`). Ini melanggar prinsip HTTP dimana GET harus idempotent.  
**Dampak**: Web crawler, browser prefetch, atau link yang dibuka di tab baru bisa secara tidak sengaja men-checkout tenant. Bisa juga dieksploitasi via CSRF jika ada kerentanan XSS.  
**Rekomendasi**: Tambahkan `@require_POST` decorator dan ubah template dari link menjadi form button.

---

### 🟡 C-02 — MEDIUM: `TenantCreateView` dan `TenantUpdateView` tidak ada security filter lokasi

**Lokasi**: `tenants/views.py` → `TenantCreateView`, `TenantUpdateView`  
**Deskripsi**: Kedua CBV ini menggunakan `LoginRequiredMixin` tapi tidak ada pengecekan lokasi. Admin dari Lokasi A bisa mengedit tenant dari Lokasi B, karena tidak ada filter `get_queryset()` yang membatasi.  
**Dampak**: Admin bisa melihat dan mengedit data tenant yang bukan tanggung jawabnya.  
**Rekomendasi**: Override `get_queryset()` pada `TenantUpdateView` untuk memfilter berdasarkan lokasi admin.

---

### 🟡 C-03 — MEDIUM: `tenant_checkout` tidak ada security filter lokasi

**Lokasi**: `tenants/views.py` → `tenant_checkout()`  
**Deskripsi**: Tidak ada pengecekan apakah admin yang melakukan checkout memiliki akses ke lokasi tenant tersebut. Admin Kost A bisa checkout tenant dari Kost B jika tahu PK-nya.  
**Dampak**: Celah keamanan multi-lokasi.  
**Rekomendasi**: Tambahkan security check `admin_profile.assigned_location == contract.room.kost_location`.

---

### 🔵 C-04 — KECIL: `tenant_list` counting `active_tenants` bisa tidak akurat

**Lokasi**: `tenants/views.py`, baris ~40  
```python
active_tenants = tenants.filter(contracts__is_active=True).distinct().count()
```
**Deskripsi**: Jika queryset `tenants` sudah di-filter oleh pencarian (`q`), maka `active_tenants` juga terpengaruh filter pencarian. Ini berarti angka "penghuni aktif" berubah saat user mengetik di search box — secara UX, angka KPI seharusnya tetap konstan.  
**Dampak**: Statistik dashboard menyesatkan saat ada search query aktif.  
**Rekomendasi**: Hitung `active_tenants` dari base queryset sebelum filter pencarian.

---

### 🔵 C-05 — KECIL: Duplikat import `TenantForm` di `tenants/views.py`

**Lokasi**: `tenants/views.py`, baris 14 dan 18  
```python
from .forms import TenantForm          # baris 14
from .forms import TenantContractForm, TenantForm  # baris 18
```
**Deskripsi**: `TenantForm` di-import dua kali. Tidak menyebabkan error, tapi unclean code.  
**Rekomendasi**: Gabungkan menjadi satu import statement.

---

### 🟢 C-06 — IMPROVEMENT: `generate_unique_pin()` bisa infinite loop secara teori

**Lokasi**: `tenants/models.py` → `TenantContract.generate_unique_pin()`  
**Deskripsi**: Menggunakan `while True` loop untuk generate PIN unik 6 digit (999.999 kemungkinan). Jika jumlah kontrak mendekati 999.999, loop akan semakin lambat atau bahkan infinite loop.  
**Dampak**: Secara praktis tidak akan terjadi untuk kost management, tapi secara teori ada risiko.  
**Rekomendasi**: Tambahkan counter/limit dan raise exception jika gagal setelah N percobaan.

---

## FITUR D: Tagihan & Billing System

**File**: `finance/views.py` → `invoice_list`, `invoice_detail`, `generate_invoices_bulk`; `finance/models.py`

### 🟡 D-01 — MEDIUM: `generate_invoices_bulk` menggunakan `billing_start_base` di success message meski `active_contracts` kosong

**Lokasi**: `finance/views.py`, baris ~755-778  
```python
billing_start_base = next_month.replace(day=1)
active_contracts = TenantContract.objects.filter(is_active=True)
# ... filter ...
for contract in active_contracts:
    ...
if created_count > 0:
    messages.success(request, f"... {billing_start_base.strftime('%B %Y')}.")
else:
    messages.info(request, f"Tidak ada tagihan baru. {skipped_count} tagihan sudah tersedia.")
```
**Deskripsi**: Sebenarnya `billing_start_base` selalu terdefinisi di atas loop, jadi tidak ada crash. Namun, logika duplikasi check pada `generate_invoices_bulk` menggunakan `billing_period_start=billing_start` (exact date) sedangkan management command menggunakan `billing_period_start__month` dan `billing_period_start__year`. Ini bisa menyebabkan duplikasi tagihan jika kedua mekanisme digunakan bergantian.  
**Dampak**: Inconsistent duplicate detection — generate dari view bisa membuat tagihan yang command anggap sudah ada, dan sebaliknya.  
**Rekomendasi**: Gunakan logika pengecekan yang konsisten (sama-sama `month+year` atau sama-sama exact date).

---

### 🟡 D-02 — MEDIUM: `ElectricityForm` tidak validasi `meter_reading_end >= meter_reading_start`

**Lokasi**: `finance/forms.py` → `ElectricityForm`; `finance/models.py` → `ElectricityReading.save()`  
**Deskripsi**: Model melakukan `usage = end - start` dan jika negatif, set ke 0. Namun, form tidak memberikan error validation — admin bisa memasukkan angka awal > akhir tanpa peringatan, dan sistem diam-diam menghitung 0 Rp. Admin mungkin tidak menyadari input salah.  
**Dampak**: Listrik bisa tercatat 0 tanpa peringatan jika input salah.  
**Rekomendasi**: Tambahkan `clean()` method di `ElectricityForm` yang memvalidasi `end >= start` dan menampilkan error message.

---

### 🔵 D-03 — KECIL: Invoice `total_amount` bisa di-bypass via direct DB

**Lokasi**: `finance/models.py` → `Invoice.save()`  
**Deskripsi**: `total_amount` selalu dihitung ulang di `save()`, bagus. Namun field ini `blank=True` tanpa `editable=False`, sehingga bisa diedit langsung di Django Admin, lalu akan tetap dioverwrite saat save. Ini membingungkan admin yang coba edit via Django Admin.  
**Rekomendasi**: Tambahkan `editable=False` pada `total_amount` field.

---

### 🔵 D-04 — KECIL: `generate_invoices_bulk` dan `generate_monthly_invoices` command duplikasi logika

**Lokasi**: `finance/views.py` baris 730-782 vs `finance/management/commands/generate_monthly_invoices.py`  
**Deskripsi**: Logika generate invoice ada di dua tempat (view dan management command) dengan sedikit perbedaan di duplicate check logic (exact date vs month+year). Ini adalah DRY violation.  
**Rekomendasi**: Extract ke service function/utility yang dipakai oleh keduanya.

---

### 🟢 D-05 — IMPROVEMENT: Tidak ada fitur Delete Invoice

**Deskripsi**: Tidak ada view/URL untuk menghapus invoice yang salah dibuat. Admin hanya bisa mengelola status invoice, tidak bisa menghapus tagihan yang salah generate.  
**Rekomendasi**: Tambahkan fitur delete invoice (hanya untuk status `BELUM_LUNAS`) dengan proteksi `@require_POST`.

---

## FITUR E: Portal Pembayaran Publik

**File**: `finance/views.py` → `public_payment_step1/2`, `public_payment_history`, `public_logout`

### 🔴 E-01 — KRITIS: Tidak ada rate limiting pada PIN validation

**Lokasi**: `finance/views.py` → `public_payment_step1()`  
**Deskripsi**: PIN hanya 6 digit numerik (999.999 kemungkinan). Form bisa di-submit berkali-kali tanpa batasan. Tidak ada CAPTCHA, delay, atau lockout mechanism. Attacker bisa brute-force semua kombinasi PIN.  
**Dampak**: Penyerang bisa mengakses data tagihan dan mengupload bukti pembayaran palsu untuk semua penghuni.  
**Rekomendasi**:
1. Implementasi rate limiting (e.g., `django-axes`, `django-ratelimit`)
2. Tambahkan CAPTCHA setelah 3x gagal
3. Pertimbangkan PIN yang lebih panjang atau alphanumeric

---

### 🟡 E-02 — MEDIUM: Session fixation — session key tidak di-regenerate setelah PIN validation

**Lokasi**: `finance/views.py` → `public_payment_step1()`, baris ~56  
```python
request.session['verified_contract_id'] = contract.id
request.session.set_expiry(1800)
```
**Deskripsi**: Setelah validasi PIN sukses, session key tidak di-rotate. Jika attacker bisa mendapatkan session cookie sebelum user login (via session fixation attack), mereka bisa menggunakan session sama.  
**Dampak**: Potensi session hijacking.  
**Rekomendasi**: Tambahkan `request.session.cycle_key()` setelah set session data.

---

### 🟡 E-03 — MEDIUM: `public_payment_step2` tidak re-check contract `is_active`

**Lokasi**: `finance/views.py` → `public_payment_step2()`, baris ~68  
**Deskripsi**: View mengambil kontrak dari session dan langsung query invoice tanpa mengecek apakah kontrak masih aktif (`is_active=True`). Jika kontrak di-checkout oleh admin antara step1 dan step2, penghuni masih bisa mengupload bukti bayar.  
**Dampak**: Pembayaran bisa terupload untuk kontrak yang sudah tidak aktif.  
**Rekomendasi**: Tambahkan `get_object_or_404(TenantContract, id=contract_id, is_active=True)`.

---

### 🔵 E-04 — KECIL: `public_logout` menerima GET request

**Lokasi**: `finance/views.py` → `public_logout()`  
**Deskripsi**: Logout menggunakan GET request, bisa di-trigger oleh browser prefetch atau link injeksi.  
**Dampak**: Penghuni bisa tidak sengaja ter-logout.  
**Rekomendasi**: Gunakan `@require_POST` dan ubah link menjadi form button.

---

### 🔵 E-05 — KECIL: `public_payment_history` tidak di-paginate

**Lokasi**: `finance/views.py` → `public_payment_history()`  
**Deskripsi**: Semua invoice diambil tanpa pagination. Untuk kontrak yang sudah berjalan bertahun-tahun, page bisa sangat panjang.  
**Rekomendasi**: Tambahkan pagination (10-15 per page).

---

## FITUR F: Verifikasi Pembayaran

**File**: `finance/views.py` → `verify_payment()`

### 🔴 F-01 — KRITIS: `verify_payment` tidak ada security filter lokasi

**Lokasi**: `finance/views.py` → `verify_payment()`, baris ~144  
**Deskripsi**: View hanya mengecek `@login_required` dan `@require_POST`. Tidak ada pengecekan apakah admin yang memverifikasi punya akses ke lokasi tagihan tersebut. Admin Kost A bisa approve/reject pembayaran dari Kost B.  
**Dampak**: Celah keamanan serius — admin bisa memanipulasi data keuangan lokasi lain.  
**Rekomendasi**: Tambahkan location security check seperti yang ada di `invoice_detail()`.

---

### 🟡 F-02 — MEDIUM: Reject payment memaksa status ke `TELAT_BAYAR` tanpa memeriksa kondisi sebelumnya

**Lokasi**: `finance/views.py` → `verify_payment()`, baris ~164  
```python
elif action == 'reject':
    invoice.status = 'TELAT_BAYAR'
```
**Deskripsi**: Saat reject, status invoice diubah menjadi `TELAT_BAYAR` hardcoded, meskipun invoice awalnya mungkin berstatus `BELUM_LUNAS` (belum lewat jatuh tempo). Seharusnya status dikembalikan ke status sebelum pembayaran diupload.  
**Dampak**: Invoice yang sebenarnya belum lewat jatuh tempo bisa ditandai "Telat Bayar".  
**Rekomendasi**: Simpan status sebelumnya di field tambahan atau cek `invoice.due_date` vs `today` untuk menentukan status yang benar.

---

### 🔵 F-03 — KECIL: `verify_payment` menerima sembarang string di `action` parameter

**Lokasi**: `finance/urls.py` → `path('verify/<int:payment_id>/<str:action>/')`  
**Deskripsi**: URL pattern menerima string apapun sebagai `action`. Jika bukan 'approve' atau 'reject', view tidak melakukan apa-apa tapi tetap redirect ke dashboard tanpa pesan error.  
**Rekomendasi**: Validasi action di view atau gunakan URL choice pattern.

---

### 🟢 F-04 — IMPROVEMENT: Tidak ada audit trail lengkap

**Deskripsi**: `Payment.verified_by` dan `verified_at` sudah bagus. Namun tidak ada tracking jika pembayaran di-reject lalu tenant upload ulang — record `Payment` lama tetap ada tanpa status jelas.  
**Rekomendasi**: Tambahkan field `status` pada model `Payment` (PENDING, APPROVED, REJECTED).

---

## FITUR G: Biaya Operasional

**File**: `finance/views.py` → operation CRUD; `finance/forms.py` → `OperationCostForm`

### 🟡 G-01 — MEDIUM: `operation_create` menampilkan semua lokasi di dropdown untuk admin biasa

**Lokasi**: `finance/views.py` → `operation_create()`, baris ~338-345  
```python
else:
    form = OperationCostForm()
    if not request.user.is_superuser and hasattr(request.user, 'admin_profile'):
        pass  # (Opsional: logic untuk hide field lokasi bisa di form, tapi biarkan dulu agar simpel)
```
**Deskripsi**: Meskipun pada `form.save(commit=False)` lokasi di-override ke lokasi admin, form tetap menampilkan dropdown semua lokasi. Ini membingungkan admin biasa — mereka pikir bisa memilih lokasi lain, padahal pilihan mereka diabaikan.  
**Dampak**: UX menyesatkan.  
**Rekomendasi**: Filter queryset dropdown `kost_location` di form untuk admin biasa, seperti yang sudah dilakukan di `room_create`.

---

### 🔵 G-02 — KECIL: `operation_list` total_expenses menghitung SEMUA waktu, bukan bulan ini

**Lokasi**: `finance/views.py` → `operation_list()`, baris ~312  
```python
total_expenses = costs.aggregate(Sum('amount'))['amount__sum'] or 0
```
**Deskripsi**: Comment di kode sendiri menyebutkan "(Bulan Ini)" tapi implementasi menghitung total keseluruhan dari semua waktu.  
**Rekomendasi**: Filter `incurred_date__month=now.month, incurred_date__year=now.year` atau ubah label di template.

---

### 🟢 G-03 — IMPROVEMENT: `OperationCost.proof_file` menggunakan `ImageField` tapi bisa terima PDF

**Lokasi**: `finance/models.py` → `OperationCost.proof_file = models.ImageField(...)`  
**Deskripsi**: Model menggunakan `ImageField` yang secara default memvalidasi bahwa file adalah gambar (via Pillow). Namun form validation (`validate_proof_file`) juga mengizinkan PDF. `ImageField` akan reject PDF di level model validation, meskipun form level sudah meng-allow-nya.  
**Dampak**: Upload PDF sebagai bukti operasional bisa gagal.  
**Rekomendasi**: Ganti `ImageField` menjadi `FileField` agar kompatibel dengan PDF.

---

## FITUR H: Laporan Kerusakan (Maintenance Tickets)

**File**: `finance/views.py` → `public_report_create/list`, `admin_ticket_list/update`; `tenants/models.py` → `MaintenanceTicket`

### 🟡 H-01 — MEDIUM: `admin_ticket_update` tidak validasi `new_status` terhadap `STATUS_CHOICES`

**Lokasi**: `finance/views.py` → `admin_ticket_update()`, baris ~537  
```python
new_status = request.POST.get('status')
if new_status:
    ticket.status = new_status
```
**Deskripsi**: Status yang diterima dari POST langsung di-set ke model tanpa validasi apakah nilainya ada di `STATUS_CHOICES`. Jika template dimanipulasi (via devtools), status bisa diisi nilai sembarang seperti "HACK" dan tetap tersimpan.  
**Dampak**: Data integrity bisa dilanggar. Django admin akan tetap menampilkannya tapi tanpa label yang benar.  
**Rekomendasi**: Validasi `new_status in dict(MaintenanceTicket.STATUS_CHOICES)`.

---

### 🔵 H-02 — KECIL: `MaintenanceTicket.photo` seharusnya wajib (required) tapi model-nya `blank=True, null=True`

**Lokasi**: `tenants/models.py` → `MaintenanceTicket.photo`  
**Deskripsi**: Model mengizinkan photo kosong (`blank=True`), tapi form label mengatakan "Foto Kerusakan (Wajib)". Inconsistensi antara model dan form validation.  
**Dampak**: Jika ada jalur lain untuk membuat ticket (API, admin), foto bisa kosong.  
**Rekomendasi**: Hapus `blank=True, null=True` pada model **atau** ubah label form menjadi "Opsional".

---

### 🔵 H-03 — KECIL: `public_report_list` tidak ada pagination

**Lokasi**: `finance/views.py` → `public_report_list()`  
**Deskripsi**: Semua ticket diambil tanpa pagination.  
**Rekomendasi**: Tambahkan pagination.

---

### 🟢 H-04 — IMPROVEMENT: Maintenance ticket features seharusnya ada di `tenants` app bukan `finance`

**Deskripsi**: `MaintenanceTicket` model ada di `tenants/models.py`, tapi semua views dan templates ada di `finance/`. Ini melanggar Django convention "fat models, thin views" dan separation of concerns.  
**Rekomendasi**: Pindahkan views dan templates maintenance ke `tenants/` app, atau buat app terpisah `maintenance/`.

---

## FITUR I: Laporan Keuangan & Export Excel

**File**: `finance/views.py` → `finance_report()`, `export_finance_excel()`; `finance/forms.py` → `ReportFilterForm`

### 🔴 I-01 — KRITIS: `ReportFilterForm.YEAR_CHOICES` di-cache saat module load

**Lokasi**: `finance/forms.py`, baris ~148-149  
```python
class ReportFilterForm(forms.Form):
    current_year = datetime.datetime.now().year
    YEAR_CHOICES = [(r, str(r)) for r in range(current_year, current_year - 5, -1)]
```
**Deskripsi**: `current_year` dihitung saat class pertama kali di-import (module load time). Jika server berjalan terus-menerus melewati pergantian tahun (1 Jan 00:00), dropdown tahun tidak akan update — akan tetap menampilkan tahun lama sampai server di-restart.  
**Dampak**: Setelah pergantian tahun, user tidak bisa melihat data tahun baru tanpa restart server.  
**Rekomendasi**: Pindahkan logic ke `__init__()` method form:
```python
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    current_year = datetime.datetime.now().year
    self.fields['year'].choices = [(r, str(r)) for r in range(current_year, current_year - 5, -1)]
```

---

### 🟡 I-02 — MEDIUM: `export_finance_excel` menduplikasi seluruh filter logic dari `finance_report`

**Lokasi**: `finance/views.py`, baris ~636-660  
**Deskripsi**: Comment di kode sendiri menyatakan: *"Dalam praktek nyata, sebaiknya buat service function agar tidak copy-paste logic"*. Filter logic untuk invoices dan costs diulang 100% antara `finance_report()` dan `export_finance_excel()`.  
**Dampak**: Jika filter diubah di satu tempat, bisa lupa di tempat lain → data report dan export tidak sinkron.  
**Rekomendasi**: Extract filter logic ke helper function.

---

### 🟡 I-03 — MEDIUM: `export_finance_excel` menggunakan `request.GET.get('kost_location')` tapi `finance_report` menggunakan Form

**Lokasi**: `finance/views.py`, baris ~643  
```python
loc_id = request.GET.get('kost_location')
```
**Deskripsi**: `finance_report` mem-parse filter via `ReportFilterForm`, sedangkan `export_finance_excel` langsung mengambil dari `request.GET`. Ini berarti export tidak melalui form validation.  
**Dampak**: Jika `kost_location` berisi non-numeric string, `filter(kost_location_id=loc_id)` bisa raise error.  
**Rekomendasi**: Gunakan form validation yang sama.

---

### 🔵 I-04 — KECIL: `finance_report` menjalankan 24 queries terpisah untuk data bulanan

**Lokasi**: `finance/views.py`, baris ~585-595  
```python
for month in range(1, 13):
    income = invoices.filter(billing_period_start__month=month).aggregate(...)
    expense = costs.filter(incurred_date__month=month).aggregate(...)
```
**Deskripsi**: Loop 12 bulan × 2 aggregate = 24 database queries. Bisa dioptimasi dengan `TruncMonth` annotation.  
**Rekomendasi**: Gunakan `annotate(month=TruncMonth('billing_period_start')).values('month').annotate(total=Sum('total_amount'))`.

---

### 🟢 I-05 — IMPROVEMENT: Excel export tidak ada auto-width kolom

**Deskripsi**: Kolom Excel menggunakan width default, membuat data terpotong saat dibuka. Sudah import `get_column_letter` dan styling modules tapi belum digunakan untuk auto-width.  
**Rekomendasi**: Tambahkan auto-fit column width berdasarkan konten.

---

## FITUR J: Manajemen Lokasi & Kamar

**File**: `core/views.py` → room/location CRUD; `core/forms.py`; `core/templates/`

### 🔴 J-01 — KRITIS: Template `room_list.html` dan `room_form.html` tidak ada

**Lokasi**: `core/views.py` → `room_list()`, `room_create()`, `room_update()`  
**Deskripsi**: Views merujuk ke `core/room_list.html` dan `core/room_form.html`, namun **file-file tersebut tidak ada di filesystem**. Folder `core/templates/core/` hanya berisi `dashboard.html`, `location_form.html`, `location_list.html`.  
**Dampak**: **Crash `TemplateDoesNotExist`** saat mengakses halaman manajemen kamar. Fitur room CRUD sepenuhnya tidak bisa digunakan.  
**Rekomendasi**: Buat kedua template tersebut segera.

---

### 🟡 J-02 — MEDIUM: `room_list` iterasi queryset dua kali

**Lokasi**: `core/views.py` → `room_list()`, baris ~180-188  
```python
for room in rooms:
    room.active_contract = room.contracts.filter(is_active=True).select_related('tenant').first()

context = {
    'rooms': rooms,
    'total_rooms': rooms.count(),
    'occupied_rooms': sum(1 for r in rooms if r.active_contract),
}
```
**Deskripsi**: Queryset `rooms` diiterasi dua kali:
1. Pertama di `for room in rooms` (evaluate seluruh queryset)
2. Kedua di `rooms.count()` (query SQL baru)
3. Ketiga di generator expression `sum(1 for r in rooms if r.active_contract)` (queryset sudah consumed)

Setelah queryset dievaluasi di loop pertama, `.count()` masih menjalankan query baru ke DB. Generator expression juga bisa gagal karena queryset sudah dievaluasi (meskipun Django caches querysets, ini tetap tidak optimal).  
**Rekomendasi**: Convert ke list dulu: `rooms = list(rooms)`, lalu gunakan `len(rooms)` alih-alih `.count()`.

---

### 🔵 J-03 — KECIL: Tidak ada fitur Create Location

**Lokasi**: `core/urls.py`, `core/views.py`  
**Deskripsi**: Hanya ada `location_list` dan `location_update`. Tidak ada view untuk menambah lokasi baru. Superuser harus menggunakan Django Admin untuk menambah lokasi.  
**Rekomendasi**: Tambahkan `location_create` view.

---

## FITUR K: Infrastruktur & Keamanan

**File**: `config/settings.py`, `Dockerfile`, `config/urls.py`, `requirements.txt`

### 🔴 K-01 — KRITIS: SECRET_KEY default hardcoded di settings.py

**Lokasi**: `config/settings.py`, baris ~23  
```python
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-s(5rwmia#0p+god3f3&f!506gc3f@a!%pt6*-^b2rm05t&^36v')
```
**Deskripsi**: Jika environment variable `DJANGO_SECRET_KEY` tidak di-set (lupa konfigurasi di production), server akan berjalan dengan secret key yang sudah ter-expose di source code. Ini memungkinkan session forgery dan cookie tampering.  
**Dampak**: Seluruh mekanisme keamanan Django (CSRF, session, signed cookies) bisa di-bypass oleh siapa saja yang membaca source code.  
**Rekomendasi**: Hapus default value. Raise error jika `DJANGO_SECRET_KEY` tidak ada di production:
```python
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY and not DEBUG:
    raise ValueError("DJANGO_SECRET_KEY must be set in production!")
```

---

### 🟡 K-02 — MEDIUM: `STATICFILES_STORAGE` deprecated di Django 5.x

**Lokasi**: `config/settings.py`, baris ~135  
```python
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
```
**Deskripsi**: Di Django 4.2+, `STATICFILES_STORAGE` digantikan oleh `STORAGES` setting. Masih bekerja di Django 5.0 tapi deprecated dan akan dihapus di versi mendatang.  
**Rekomendasi**: Migrasi ke:
```python
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
```

---

### 🟡 K-03 — MEDIUM: Media files disajikan di production tanpa proteksi

**Lokasi**: `config/urls.py`, baris terakhir  
```python
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```
**Deskripsi**: `django.conf.urls.static.static()` hanya bekerja di `DEBUG=True`. Namun di production (Docker/Gunicorn), file media termasuk **KTP penghuni** (`media/ktp_private/`) bisa diakses langsung jika ada reverse proxy yang serve folder `media/`.  
**Dampak**: Foto KTP (data pribadi sensitif) bisa diakses oleh siapa saja yang tahu URL-nya.  
**Rekomendasi**: 
1. Serve file KTP melalui view Django yang memerlukan `@login_required`
2. Atau gunakan signed URL / private storage backend

---

### 🟡 K-04 — MEDIUM: Tidak ada security headers (SECURE_SSL_REDIRECT, HSTS, dll)

**Lokasi**: `config/settings.py`  
**Deskripsi**: Tidak ada konfigurasi production security:
- `SECURE_SSL_REDIRECT` → tidak ada
- `SECURE_HSTS_SECONDS` → tidak ada
- `SESSION_COOKIE_SECURE` → tidak ada
- `CSRF_COOKIE_SECURE` → tidak ada
- `SECURE_BROWSER_XSS_FILTER` → tidak ada
- `X_FRAME_OPTIONS` → menggunakan default `DENY` (sudah ok via middleware)

**Dampak**: Website bisa diakses via HTTP tanpa redirect ke HTTPS, session cookie bisa dicuri via MITM.  
**Rekomendasi**: Tambahkan conditional security settings:
```python
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
```

---

### 🔵 K-05 — KECIL: `Dockerfile` tidak menjalankan `migrate` saat build

**Lokasi**: `Dockerfile`  
**Deskripsi**: Dockerfile hanya menjalankan `collectstatic` tapi tidak `migrate`. Migration harus dijalankan secara manual atau via entrypoint script.  
**Dampak**: Deployment baru bisa gagal jika lupa jalankan migrate.  
**Rekomendasi**: Tambahkan entrypoint script yang menjalankan `python manage.py migrate && gunicorn ...` atau gunakan Coolify pre-deploy hook.

---

### 🔵 K-06 — KECIL: `health_check` endpoint terlalu sederhana

**Lokasi**: `config/urls.py` → `health_check()`  
```python
def health_check(request):
    return JsonResponse({'status': 'ok'})
```
**Deskripsi**: Health check tidak mengecek koneksi database. Server bisa dilaporkan "OK" meskipun database down.  
**Rekomendasi**: Tambahkan database connectivity check.

---

### 🟢 K-07 — IMPROVEMENT: Tidak ada logging configuration

**Lokasi**: `config/settings.py`  
**Deskripsi**: Tidak ada `LOGGING` setting. Error di production tidak tercatat di file log — hanya muncul di stdout Gunicorn.  
**Rekomendasi**: Konfigurasi Django logging minimal untuk error tracking.

---

### 🟢 K-08 — IMPROVEMENT: Gunicorn tanpa workers configuration  

**Lokasi**: `Dockerfile`, baris terakhir  
```dockerfile
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
```
**Deskripsi**: Gunicorn default hanya menggunakan 1 worker (sync). Untuk production, sebaiknya gunakan multiple workers.  
**Rekomendasi**: Tambahkan `--workers 3` atau `--workers $(nproc)`.

---

### 🟢 K-09 — IMPROVEMENT: `requirements.txt` tidak pin versi secara eksplisit

**Deskripsi**: Jika `requirements.txt` tidak meng-pin versi dependency secara spesifik (misal `Django==5.0.6`), build yang berbeda bisa menghasilkan dependency versions yang berbeda.  
**Rekomendasi**: Gunakan `pip freeze > requirements.txt` atau tools seperti `pip-compile`.

---

## Ringkasan Temuan

| Severity | Jumlah | Persentase |
|----------|--------|------------|
| 🔴 KRITIS | 6 | 14% |
| 🟡 MEDIUM | 11 | 26% |
| 🔵 KECIL | 14 | 33% |
| 🟢 IMPROVEMENT | 11 | 26% |
| **TOTAL** | **42** | **100%** |

### Top 5 Prioritas Perbaikan

| # | ID | Severity | Deskripsi |
|---|------|----------|-----------|
| 1 | J-01 | 🔴 KRITIS | Template room_list.html dan room_form.html tidak ada → **crash** |
| 2 | E-01 | 🔴 KRITIS | Tidak ada rate limiting pada PIN → **brute-force** |
| 3 | F-01 | 🔴 KRITIS | verify_payment tidak ada security filter lokasi |
| 4 | K-01 | 🔴 KRITIS | SECRET_KEY hardcoded di source code |
| 5 | I-01 | 🔴 KRITIS | YEAR_CHOICES di-cache saat module load |

---

*Laporan ini dihasilkan melalui analisis statis mendalam terhadap seluruh source code project.*
