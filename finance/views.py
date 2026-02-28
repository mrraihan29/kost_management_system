from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from core.models import Room, KostLocation
from tenants.models import TenantContract, MaintenanceTicket
from .models import Invoice, Payment, ElectricityReading, OperationCost
from .forms import PinValidationForm, PaymentUploadForm, ElectricityForm, OperationCostForm, MaintenanceForm, ReportFilterForm
from .services import sync_overdue_invoice_statuses
from config.security import check_rate_limit, record_failed_attempt, reset_rate_limit, log_action
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q, Sum, Count
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from dateutil.relativedelta import relativedelta
import datetime
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def public_payment_step1(request):
    """
    Langkah 1: Halaman Validasi PIN
    SEC-01: Dilindungi rate limiting (5 percobaan / 15 menit per IP)
    """
    # SEC-01: Cek apakah IP sudah diblokir karena terlalu banyak gagal
    is_blocked, attempts, retry_after = check_rate_limit(
        request, key_prefix='pin_attempt', max_attempts=5, window=900
    )
    if is_blocked:
        retry_minutes = max(1, retry_after // 60)
        messages.error(
            request,
            f"Terlalu banyak percobaan gagal. Coba lagi dalam {retry_minutes} menit."
        )
        form = PinValidationForm()
        return render(request, 'finance/step1_pin.html', {'form': form})

    if request.method == 'POST':
        form = PinValidationForm(request.POST)
        if form.is_valid():
            location = form.cleaned_data['kost_location']
            room_num = form.cleaned_data['room_number']
            pin = form.cleaned_data['pin']

            # --- LOGIKA VALIDASI ---
            # 1. Cari Kamar yang cocok (Lokasi & No Kamar)
            try:
                room = Room.objects.get(kost_location=location, room_number__iexact=room_num)
            except Room.DoesNotExist:
                # SEC-01: Catat percobaan gagal
                record_failed_attempt(request, key_prefix='pin_attempt', window=900)
                messages.error(request, "Kamar tidak ditemukan di lokasi tersebut.")
                return render(request, 'finance/step1_pin.html', {'form': form})

            # 2. Cari Kontrak Aktif di kamar itu dengan PIN yang cocok
            try:
                contract = TenantContract.objects.get(room=room, payment_pin=pin, is_active=True)
            except TenantContract.DoesNotExist:
                # SEC-01: Catat percobaan gagal
                record_failed_attempt(request, key_prefix='pin_attempt', window=900)
                messages.error(request, "PIN salah atau Kontrak tidak aktif.")
                return render(request, 'finance/step1_pin.html', {'form': form})

            # --- JIKA SUKSES ---
            # SEC-01: Reset counter karena berhasil
            reset_rate_limit(request, key_prefix='pin_attempt')

            # Simpan ID kontrak di Session
            request.session['verified_contract_id'] = contract.id
            request.session.set_expiry(1800)  # 30 menit

            # SEC-12: Log successful PIN authentication
            log_action(request, 'PIN_AUTH_SUCCESS',
                       f'Contract #{contract.id}',
                       f'Tenant: {contract.tenant.full_name}, Room: {room.room_number}')

            messages.success(request, f"Halo, {contract.tenant.full_name}! Silakan upload bukti bayar.")
            return redirect('public_payment_step2')

    else:
        form = PinValidationForm()

    return render(request, 'finance/step1_pin.html', {'form': form})


def public_payment_step2(request):
    """
    Langkah 2: Halaman Upload File
    """
    # Cek apakah user punya "tiket" di sakunya (Session)
    contract_id = request.session.get('verified_contract_id')
    if not contract_id:
        messages.error(request, "Sesi habis. Silakan masukkan PIN ulang.")
        return redirect('public_payment_step1')

    contract = get_object_or_404(TenantContract, id=contract_id, is_active=True)
    active_invoice = Invoice.objects.filter(
        contract=contract
    ).exclude(status__in=['LUNAS', 'MENUNGGU_VERIFIKASI']).order_by('-billing_period_start').first()

    if request.method == 'POST':
        form = PaymentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            # --- LOGIKA SIMPAN ---
            payment = form.save(commit=False)
            
            # Jika tidak ada invoice aktif, buat invoice baru (opsional, tapi sementara kita wajibkan ada invoice)
            if not active_invoice:
                messages.error(request, "Tidak ada tagihan aktif yang perlu dibayar.")
                return redirect('public_payment_step2')

            payment.invoice = active_invoice
            payment.save()

            # Update Status Invoice jadi 'MENUNGGU VERIFIKASI'
            active_invoice.status = 'MENUNGGU_VERIFIKASI'
            active_invoice.save()

            # Hapus sesi (Selesai)
            del request.session['verified_contract_id']
            
            return render(request, 'finance/success.html')
    else:
        form = PaymentUploadForm()

    context = {
        'form': form,
        'tenant_name': contract.tenant.full_name,
        'room_info': str(contract.room),
        'invoice': active_invoice
    }
    return render(request, 'finance/step2_upload.html', context)

def public_payment_history(request):
    """
    Halaman Riwayat Pembayaran (Publik - Session Based)
    """
    # 1. Cek Keamanan Sesi (Wajib sudah validasi PIN)
    contract_id = request.session.get('verified_contract_id')
    if not contract_id:
        messages.error(request, "Sesi habis. Silakan masukkan PIN ulang.")
        return redirect('public_payment_step1')

    # 2. Ambil Data
    contract = get_object_or_404(TenantContract, id=contract_id)
    
    # Ambil SEMUA invoice, urutkan dari yang terbaru
    invoices = Invoice.objects.filter(contract=contract).order_by('-billing_period_start')

    # E-05 fix: Pagination untuk riwayat pembayaran
    paginator = Paginator(invoices, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'contract': contract,
        'invoices': page_obj,
        'page_obj': page_obj,
        'hide_sidebar': True # Pastikan sidebar admin tidak muncul
    }
    return render(request, 'finance/payment_history.html', context)

def public_logout(request):
    """
    Logout Portal Publik — Hapus session penghuni (B-FLOW-04)
    """
    if 'verified_contract_id' in request.session:
        del request.session['verified_contract_id']
    messages.info(request, "Anda telah keluar. Silakan masukkan PIN untuk masuk kembali.")
    return redirect('public_payment_step1')

@require_POST
@login_required(login_url='/accounts/login/')
def verify_payment(request, payment_id, action):
    """
    Logika Verifikasi (Approve/Reject) FR-03
    """
    payment = get_object_or_404(Payment, id=payment_id)
    invoice = payment.invoice

    # Security: Cek kepemilikan lokasi (F-01 fix)
    if not request.user.is_superuser:
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            if invoice.contract.room.kost_location != request.user.admin_profile.assigned_location:
                messages.error(request, "Anda tidak memiliki akses untuk memverifikasi pembayaran ini.")
                return redirect('dashboard')
        else:
            messages.error(request, "Akun Anda belum ditugaskan ke lokasi manapun.")
            return redirect('dashboard')

    # F-03 fix: Validasi action
    if action not in ('approve', 'reject'):
        messages.error(request, "Aksi tidak valid.")
        return redirect('dashboard')

    if action == 'approve':
        # Update Invoice jadi LUNAS
        invoice.status = 'LUNAS'
        invoice.save()

        # Update Payment Info
        payment.verified_by = request.user
        payment.verified_at = timezone.now()
        payment.save()

        # SEC-12: Audit log approval
        log_action(request, 'PAYMENT_APPROVED',
                   f'Invoice #{invoice.id}',
                   f'Tenant: {invoice.contract.tenant.full_name}, Amount: {invoice.total_amount}')

        messages.success(request, f"Pembayaran {invoice.contract.tenant.full_name} disetujui.")

    elif action == 'reject':
        # F-02 fix: Kembalikan status berdasarkan apakah sudah lewat jatuh tempo
        today = timezone.now().date()
        if invoice.due_date < today:
            invoice.status = 'TELAT_BAYAR'
        else:
            invoice.status = 'BELUM_LUNAS'
        invoice.save()

        # Update Payment Info (B-FLOW-03 fix: Custom rejection note)
        payment.verified_by = request.user
        payment.verified_at = timezone.now()
        custom_note = request.POST.get('rejection_note', '').strip()
        payment.rejection_note = custom_note if custom_note else "Bukti tidak valid (Ditolak Admin)"
        payment.save()

        # SEC-12: Audit log rejection
        log_action(request, 'PAYMENT_REJECTED',
                   f'Invoice #{invoice.id}',
                   f'Tenant: {invoice.contract.tenant.full_name}, Reason: {payment.rejection_note}')

        messages.error(request, f"Pembayaran {invoice.contract.tenant.full_name} DITOLAK.")

    return redirect('dashboard')

@login_required(login_url='/accounts/login/')
def invoice_list(request):
    """
    Halaman Daftar Semua Tagihan (Admin) - FIXED SECURITY
    """
    sync_overdue_invoice_statuses()

    status_filter = request.GET.get('status')
    search_query = request.GET.get('q')

    # 1. Base Query (C-PERF-03 fix: select_related untuk menghindari N+1)
    invoices = Invoice.objects.select_related(
        'contract__tenant', 'contract__room__kost_location'
    ).prefetch_related('payments').order_by('-due_date')

    # 2. SECURITY FILTER (BUG FIX)
    # Admin biasa HANYA boleh melihat tagihan di lokasinya
    if not request.user.is_superuser:
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            user_location = request.user.admin_profile.assigned_location
            invoices = invoices.filter(contract__room__kost_location=user_location)
        else:
            # Admin tanpa lokasi = tidak lihat apa-apa
            invoices = invoices.none()

    # 3. Filter by Status
    if status_filter:
        invoices = invoices.filter(status=status_filter)

    # 4. Search
    if search_query:
        invoices = invoices.filter(
            Q(contract__tenant__full_name__icontains=search_query) |
            Q(contract__room__room_number__icontains=search_query)
        )

    # C-PAGE-02: Pagination
    paginator = Paginator(invoices, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'invoices': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
        'current_status': status_filter
    }
    return render(request, 'finance/invoice_list.html', context)

@login_required(login_url='/accounts/login/')
def invoice_detail(request, pk):
    """
    Halaman Detail Tagihan & Input Listrik (Admin)
    """
    invoice = get_object_or_404(Invoice, pk=pk)
    
    # Security: Cek kepemilikan lokasi (A-SEC-04)
    if not request.user.is_superuser:
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            if invoice.contract.room.kost_location != request.user.admin_profile.assigned_location:
                messages.error(request, "Anda tidak memiliki akses ke tagihan ini.")
                return redirect('invoice_list')
        else:
            messages.error(request, "Akun Anda belum ditugaskan ke lokasi manapun.")
            return redirect('dashboard')

    # Cek apakah sudah ada catatan listrik?
    electricity = ElectricityReading.objects.filter(invoice=invoice).first()

    # Handle Form Listrik
    if request.method == 'POST':
        if electricity:
            form = ElectricityForm(request.POST, instance=electricity)
        else:
            form = ElectricityForm(request.POST)
        
        if form.is_valid():
            reading = form.save(commit=False)
            reading.invoice = invoice # Hubungkan ke invoice ini
            reading.save() # Logic save() di models.py akan otomatis hitung total
            messages.success(request, "Data listrik berhasil disimpan & tagihan diupdate.")
            return redirect('invoice_detail', pk=pk)
    else:
        # Pre-fill form jika data sudah ada
        if electricity:
            form = ElectricityForm(instance=electricity)
        else:
            # Default tarif dari lokasi kost
            default_rate = invoice.contract.room.kost_location.electricity_rate_per_kwh
            form = ElectricityForm(initial={'rate_per_kwh': default_rate})

    context = {
        'invoice': invoice,
        'form': form,
        'electricity': electricity
    }
    return render(request, 'finance/invoice_detail.html', context)

@login_required(login_url='/accounts/login/')
def operation_list(request):
    """
    Halaman Daftar Biaya Operasional
    """
    costs = OperationCost.objects.select_related(
        'kost_location', 'admin'
    ).order_by('-incurred_date')

    # Filter Lokasi (Security: Admin Ancol cuma lihat Ancol)
    if not request.user.is_superuser:
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            costs = costs.filter(kost_location=request.user.admin_profile.assigned_location)
        else:
            costs = costs.none()

    total_expenses = costs.aggregate(Sum('amount'))['amount__sum'] or 0

    # C-PAGE-03: Pagination
    paginator = Paginator(costs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'costs': page_obj,
        'page_obj': page_obj,
        'total_expenses': total_expenses
    }
    return render(request, 'finance/operation_list.html', context)

@login_required(login_url='/accounts/login/')
def operation_create(request):
    """
    Form Tambah Biaya Baru
    """
    if request.method == 'POST':
        form = OperationCostForm(request.POST, request.FILES)
        if form.is_valid():
            cost = form.save(commit=False)
            cost.admin = request.user # Catat siapa yang input
            
            # Security: Jika bukan superuser, paksa lokasi sesuai admin
            if not request.user.is_superuser and hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
                cost.kost_location = request.user.admin_profile.assigned_location
            
            cost.save()
            messages.success(request, "Pengeluaran berhasil dicatat.")
            return redirect('operation_list')
    else:
        form = OperationCostForm()
        # G-01 fix: Filter dropdown lokasi untuk admin biasa
        if not request.user.is_superuser and hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            form.fields['kost_location'].queryset = KostLocation.objects.filter(pk=request.user.admin_profile.assigned_location.pk)
            form.fields['kost_location'].initial = request.user.admin_profile.assigned_location

    return render(request, 'finance/operation_form.html', {'form': form, 'title': 'Catat Pengeluaran'})

@login_required(login_url='/accounts/login/')
def operation_update(request, pk):
    """
    Form Edit Biaya Operasional (B-CRUD-02)
    """
    cost = get_object_or_404(OperationCost, pk=pk)
    
    # Security: Cek kepemilikan lokasi
    if not request.user.is_superuser:
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            if cost.kost_location != request.user.admin_profile.assigned_location:
                messages.error(request, "Anda tidak memiliki akses ke data ini.")
                return redirect('operation_list')
        else:
            return redirect('dashboard')
    
    if request.method == 'POST':
        form = OperationCostForm(request.POST, request.FILES, instance=cost)
        if form.is_valid():
            updated_cost = form.save(commit=False)
            # Security: Jika bukan superuser, paksa lokasi sesuai admin
            if not request.user.is_superuser and hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
                updated_cost.kost_location = request.user.admin_profile.assigned_location
            updated_cost.save()
            messages.success(request, "Data pengeluaran berhasil diperbarui.")
            return redirect('operation_list')
    else:
        form = OperationCostForm(instance=cost)

    return render(request, 'finance/operation_form.html', {'form': form, 'title': 'Edit Pengeluaran'})

@require_POST
@login_required(login_url='/accounts/login/')
def operation_delete(request, pk):
    """
    Hapus Biaya Operasional (B-CRUD-02)
    """
    cost = get_object_or_404(OperationCost, pk=pk)
    
    # Security: Cek kepemilikan lokasi
    if not request.user.is_superuser:
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            if cost.kost_location != request.user.admin_profile.assigned_location:
                messages.error(request, "Anda tidak memiliki akses ke data ini.")
                return redirect('operation_list')
        else:
            return redirect('dashboard')
    
    cost.delete()
    # SEC-12: Audit log deletion
    log_action(request, 'OPERATION_COST_DELETED',
               f'OperationCost #{pk}',
               f'Category: {cost.get_category_display()}, Amount: {cost.amount}')
    messages.success(request, "Data pengeluaran berhasil dihapus.")
    return redirect('operation_list')

@login_required(login_url='/accounts/login/')
def print_receipt(request, pk):
    """
    Halaman Cetak Kwitansi (Hanya untuk yang LUNAS)
    """
    invoice = get_object_or_404(Invoice, pk=pk)
    
    # Security: Cek kepemilikan lokasi (A-SEC-05)
    if not request.user.is_superuser:
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            if invoice.contract.room.kost_location != request.user.admin_profile.assigned_location:
                messages.error(request, "Anda tidak memiliki akses ke kwitansi ini.")
                return redirect('invoice_list')
        else:
            return redirect('dashboard')

    # Security: Hanya boleh cetak jika sudah LUNAS
    if invoice.status != 'LUNAS':
        messages.error(request, "Hanya tagihan LUNAS yang bisa dicetak kwitansinya.")
        return redirect('invoice_list')

    context = {
        'invoice': invoice,
        'payment': invoice.payments.last(), # Ambil pembayaran terakhir yang sukses
        'admin_name': request.user.get_full_name() or request.user.username,
        'print_date': timezone.now()
    }
    return render(request, 'finance/print_receipt.html', context)

def public_report_create(request):
    """
    Halaman Buat Laporan Kerusakan (Publik)
    """
    # Cek Sesi (Keamanan)
    contract_id = request.session.get('verified_contract_id')
    if not contract_id:
        messages.error(request, "Sesi habis. Masukkan PIN ulang.")
        return redirect('public_payment_step1')

    contract = get_object_or_404(TenantContract, id=contract_id)

    if request.method == 'POST':
        form = MaintenanceForm(request.POST, request.FILES)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.contract = contract
            ticket.save()
            messages.success(request, "Laporan kerusakan berhasil dikirim! Admin akan segera mengecek.")
            return redirect('public_report_list')
    else:
        form = MaintenanceForm()

    return render(request, 'finance/report_form.html', {
        'form': form, 
        'contract': contract,
        'hide_sidebar': True
    })

def public_report_list(request):
    """
    Halaman Riwayat Laporan Kerusakan (Publik)
    """
    contract_id = request.session.get('verified_contract_id')
    if not contract_id:
        return redirect('public_payment_step1')

    contract = get_object_or_404(TenantContract, id=contract_id)
    tickets = MaintenanceTicket.objects.filter(contract=contract).order_by('-created_at')

    # H-03 fix: Pagination untuk riwayat laporan
    paginator = Paginator(tickets, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'finance/report_list.html', {
        'tickets': page_obj,
        'page_obj': page_obj,
        'contract': contract,
        'hide_sidebar': True
    })
    
@login_required(login_url='/accounts/login/')
def admin_ticket_list(request):
    """
    Daftar Laporan Kerusakan (Dengan Filter Status & Kamar)
    """
    # 1. Base Query (C-PERF-05 fix: select_related)
    tickets = MaintenanceTicket.objects.select_related(
        'contract__tenant', 'contract__room__kost_location'
    ).order_by('-created_at')
    
    # 2. Ambil Daftar Kamar untuk Dropdown Filter
    # (Hanya tampilkan kamar yang ada di lokasi admin tersebut)
    rooms = Room.objects.all().order_by('room_number')

    # 3. Security Filter (Lokasi)
    if not request.user.is_superuser:
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            user_loc = request.user.admin_profile.assigned_location
            tickets = tickets.filter(contract__room__kost_location=user_loc)
            rooms = rooms.filter(kost_location=user_loc)
        else:
            tickets = tickets.none()
            rooms = rooms.none()

    # 4. Filter Status (URL ?status=...)
    status_filter = request.GET.get('status')
    if status_filter:
        tickets = tickets.filter(status=status_filter)

    # 5. Filter Kamar (URL ?room=ID) - FITUR BARU
    room_filter = request.GET.get('room')
    if room_filter:
        tickets = tickets.filter(contract__room_id=room_filter)

    # C-PAGE-04: Pagination
    paginator = Paginator(tickets, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'tickets': page_obj,
        'page_obj': page_obj,
        'rooms': rooms,
        'current_status': status_filter,
        'current_room': int(room_filter) if room_filter else None
    }
    return render(request, 'finance/ticket_list.html', context)

@login_required(login_url='/accounts/login/')
def admin_ticket_update(request, pk):
    """
    Update Status Tiket & Catat Tanggal Selesai
    """
    ticket = get_object_or_404(MaintenanceTicket, pk=pk)

    # Security: Cek kepemilikan lokasi (A-SEC-06)
    if not request.user.is_superuser:
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            if ticket.contract.room.kost_location != request.user.admin_profile.assigned_location:
                messages.error(request, "Anda tidak memiliki akses ke tiket ini.")
                return redirect('ticket_list')
        else:
            return redirect('dashboard')

    if request.method == 'POST':
        new_status = request.POST.get('status')
        # H-01 fix: Validasi status terhadap STATUS_CHOICES
        valid_statuses = dict(MaintenanceTicket.STATUS_CHOICES)
        if new_status and new_status in valid_statuses:
            ticket.status = new_status
            
            # LOGIKA BARU: Jika Selesai, catat waktunya
            if new_status == 'SELESAI':
                ticket.completion_date = timezone.now()
            elif new_status != 'SELESAI':
                # Jika status dikembalikan ke Proses/Pending, hapus tanggal selesainya
                ticket.completion_date = None
                
            ticket.save()
            messages.success(request, f"Status laporan '{ticket.title}' diperbarui.")
            return redirect('ticket_list')
        elif new_status:
            messages.error(request, "Status yang dipilih tidak valid.")
            return redirect('ticket_list')

    return render(request, 'finance/ticket_detail.html', {'ticket': ticket})

@login_required(login_url='/accounts/login/')
def finance_report(request):
    """
    Dashboard Analisis Keuangan (Multi-Chart & Filter)
    """
    # 1. Handle Filter
    current_year = datetime.datetime.now().year
    form = ReportFilterForm(request.GET or {'year': current_year})
    
    selected_year = current_year
    selected_location = None

    if form.is_valid():
        selected_year = int(form.cleaned_data['year'])
        selected_location = form.cleaned_data['kost_location']

    # 2. Base Query
    invoices = Invoice.objects.filter(billing_period_start__year=selected_year, status='LUNAS')
    costs = OperationCost.objects.filter(incurred_date__year=selected_year)

    # Filter Lokasi (Logic Security + Logic Pilihan User)
    location_label = "Semua Lokasi"
    
    if not request.user.is_superuser:
        # Jika Admin biasa, paksa filter ke lokasinya
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            user_loc = request.user.admin_profile.assigned_location
            invoices = invoices.filter(contract__room__kost_location=user_loc)
            costs = costs.filter(kost_location=user_loc)
            location_label = user_loc.name
            # Hide field lokasi di form nanti via template logic
    elif selected_location:
        # Jika Superuser memilih lokasi tertentu
        invoices = invoices.filter(contract__room__kost_location=selected_location)
        costs = costs.filter(kost_location=selected_location)
        location_label = selected_location.name

    # 3. Aggregasi Bulanan (Untuk Grafik Trend)
    monthly_data = []
    total_income = 0
    total_expense = 0

    for month in range(1, 13):
        income = invoices.filter(billing_period_start__month=month).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        expense = costs.filter(incurred_date__month=month).aggregate(Sum('amount'))['amount__sum'] or 0
        profit = income - expense
        
        monthly_data.append({
            'month_name': datetime.date(1900, month, 1).strftime('%B'),
            'income': float(income),
            'expense': float(expense),
            'profit': float(profit)
        })
        total_income += income
        total_expense += expense

    # 4. Aggregasi Kategori Pengeluaran (Untuk Pie Chart)
    # Contoh: Listrik: 5jt, Air: 1jt
    expense_breakdown = costs.values('category').annotate(total=Sum('amount')).order_by('-total')
    
    # Siapkan data JSON untuk Chart.js
    chart_labels = [d['month_name'] for d in monthly_data]
    chart_income = [d['income'] for d in monthly_data]
    chart_expense = [d['expense'] for d in monthly_data]
    
    pie_labels = [item['category'] for item in expense_breakdown]
    pie_data = [float(item['total']) for item in expense_breakdown]

    context = {
        'form': form,
        'year': selected_year,
        'location_label': location_label,
        'total_income': total_income,
        'total_expense': total_expense,
        'net_profit': total_income - total_expense,
        'monthly_data': monthly_data,
        # Data Charts
        'chart_labels': chart_labels,
        'chart_income': chart_income,
        'chart_expense': chart_expense,
        'pie_labels': pie_labels,
        'pie_data': pie_data,
    }
    return render(request, 'finance/report_dashboard.html', context)

@login_required(login_url='/accounts/login/')
def export_finance_excel(request):
    """
    Export Excel Professional (.xlsx) dengan Multiple Sheets
    """
    # ... (Ambil logika filter yang SAMA PERSIS dengan finance_report di atas) ...
    # Agar kode singkat, saya asumsikan variabel 'invoices' dan 'costs' sudah terfilter
    # (Dalam praktek nyata, sebaiknya buat service function agar tidak copy-paste logic)
    
    # --- REPEAT LOGIC FILTER (Singkat) ---
    year = int(request.GET.get('year', datetime.datetime.now().year))
    loc_id = request.GET.get('kost_location')
    
    # C-PERF-02 fix: select_related untuk Excel export
    invoices = Invoice.objects.filter(
        billing_period_start__year=year, status='LUNAS'
    ).select_related(
        'contract__tenant', 'contract__room'
    ).prefetch_related('payments__verified_by')
    costs = OperationCost.objects.filter(
        incurred_date__year=year
    ).select_related('kost_location', 'admin')
    
    if not request.user.is_superuser:
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            loc = request.user.admin_profile.assigned_location
            invoices = invoices.filter(contract__room__kost_location=loc)
            costs = costs.filter(kost_location=loc)
    elif loc_id:
        invoices = invoices.filter(contract__room__kost_location_id=loc_id)
        costs = costs.filter(kost_location_id=loc_id)
    # -------------------------------------

    # SETUP WORKBOOK
    wb = openpyxl.Workbook()
    
    # --- SHEET 1: RINGKASAN ---
    ws1 = wb.active
    ws1.title = "Ringkasan Bulanan"
    
    # Header Style
    font_bold = Font(bold=True)
    headers = ['Bulan', 'Pemasukan', 'Pengeluaran', 'Profit Bersih']
    ws1.append(headers)
    for cell in ws1[1]: cell.font = font_bold

    # Isi Data
    for month in range(1, 13):
        income = invoices.filter(billing_period_start__month=month).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        expense = costs.filter(incurred_date__month=month).aggregate(Sum('amount'))['amount__sum'] or 0
        profit = income - expense
        month_name = datetime.date(1900, month, 1).strftime('%B')
        ws1.append([month_name, income, expense, profit])

    # --- SHEET 2: DETAIL PEMASUKAN ---
    ws2 = wb.create_sheet(title="Rincian Pemasukan")
    ws2.append(['Tanggal', 'Penghuni', 'Kamar', 'Jumlah', 'Admin Verifikasi'])
    for cell in ws2[1]: cell.font = font_bold
    
    for inv in invoices.order_by('billing_period_start'):
        # Ambil admin yang verifikasi pembayaran terakhir
        verifier = inv.payments.last().verified_by.username if inv.payments.exists() and inv.payments.last().verified_by else "-"
        ws2.append([
            inv.billing_period_start,
            inv.contract.tenant.full_name,
            inv.contract.room.room_number,
            inv.total_amount,
            verifier
        ])

    # --- SHEET 3: DETAIL PENGELUARAN ---
    ws3 = wb.create_sheet(title="Rincian Operasional")
    ws3.append(['Tanggal', 'Kategori', 'Keterangan', 'Jumlah', 'Admin'])
    for cell in ws3[1]: cell.font = font_bold

    for cost in costs.order_by('incurred_date'):
        ws3.append([
            cost.incurred_date,
            cost.get_category_display(),
            cost.description,
            cost.amount,
            cost.admin.username if cost.admin else "-"
        ])

    # RESPONSE
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="Laporan_Keuangan_EKM_{year}.xlsx"'
    wb.save(response)
    return response

@login_required(login_url='/accounts/login/')
def generate_invoices_bulk(request):
    """
    Fitur: Generate Tagihan Massal via Tombol Dashboard
    """
    if request.method == 'POST':
        # 1. Tentukan Periode (Logika: Bulan Depan dari Hari Ini)
        # Kenapa bulan depan? Karena biasanya admin menyiapkan tagihan sebelum bulan berjalan.
        today = timezone.now().date()
        next_month = today + relativedelta(months=1)
        billing_start_base = next_month.replace(day=1) # Tgl 1 Bulan Depan
        
        # 2. Ambil semua kontrak aktif
        active_contracts = TenantContract.objects.filter(is_active=True)
        
        # A-DATA-04 fix: Filter berdasarkan lokasi admin
        if not request.user.is_superuser:
            if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
                active_contracts = active_contracts.filter(
                    room__kost_location=request.user.admin_profile.assigned_location
                )
            else:
                active_contracts = active_contracts.none()
        
        created_count = 0
        skipped_count = 0

        for contract in active_contracts:
            location_name = (contract.room.kost_location.name or '').strip().lower()
            is_ancol = 'ancol' in location_name

            if is_ancol:
                # ANCOL: siklus per-tenant berdasarkan tanggal mulai kontrak
                # Contoh: mulai tgl 10, maka jatuh tempo tetap tgl 10 setiap bulan
                try:
                    billing_start = billing_start_base.replace(day=contract.start_date.day)
                except ValueError:
                    # Fallback untuk tanggal 29/30/31 di bulan pendek
                    billing_start = billing_start_base.replace(day=28)
                due_date = billing_start
            else:
                # NON-ANCOL: serentak mengikuti tanggal global sistem (start bulan)
                billing_start = billing_start_base
                # Ketentuan existing: jatuh tempo H+10 dari tanggal muncul tagihan
                due_date = billing_start + relativedelta(days=10)

            # Cek apakah sudah ada tagihan di periode tersebut?
            exists = Invoice.objects.filter(
                contract=contract,
                billing_period_start=billing_start
            ).exists()

            if not exists:
                Invoice.objects.create(
                    contract=contract,
                    billing_period_start=billing_start,
                    due_date=due_date,
                    base_rent_amount=contract.monthly_rent_amount,
                    electricity_bill_amount=0,
                    total_amount=contract.monthly_rent_amount,
                    status='BELUM_LUNAS'
                )
                created_count += 1
            else:
                skipped_count += 1

        if created_count > 0:
            messages.success(request, f"Berhasil membuat {created_count} tagihan baru untuk periode {billing_start_base.strftime('%B %Y')}.")
        else:
            messages.info(request, f"Tidak ada tagihan baru. {skipped_count} tagihan sudah tersedia.")
            
    return redirect('invoice_list')