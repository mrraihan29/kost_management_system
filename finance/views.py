from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from core.models import Room
from tenants.models import TenantContract
from .models import Invoice, Payment, ElectricityReading, OperationCost
from .forms import PinValidationForm, PaymentUploadForm, ElectricityForm, OperationCostForm
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q, Sum
from django.http import HttpResponseForbidden
from .forms import MaintenanceForm
from tenants.models import MaintenanceTicket

def public_payment_step1(request):
    """
    Langkah 1: Halaman Validasi PIN
    """
    # Jika form di-submit (POST)
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
                messages.error(request, "Kamar tidak ditemukan di lokasi tersebut.")
                return render(request, 'finance/step1_pin.html', {'form': form})

            # 2. Cari Kontrak Aktif di kamar itu dengan PIN yang cocok
            try:
                contract = TenantContract.objects.get(room=room, payment_pin=pin, is_active=True)
            except TenantContract.DoesNotExist:
                messages.error(request, "PIN salah atau Kontrak tidak aktif.")
                return render(request, 'finance/step1_pin.html', {'form': form})

            # --- JIKA SUKSES ---
            # Simpan ID kontrak di Session (Saku Browser)
            request.session['verified_contract_id'] = contract.id
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

    contract = get_object_or_404(TenantContract, id=contract_id)

    # Cari tagihan AKTIF (Belum Lunas / Telat Bayar)
    # Kita ambil tagihan terbaru yang belum lunas
    active_invoice = Invoice.objects.filter(
        contract=contract
    ).exclude(status='LUNAS').order_by('-billing_period_start').first()

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

    context = {
        'contract': contract,
        'invoices': invoices,
        'hide_sidebar': True # Pastikan sidebar admin tidak muncul
    }
    return render(request, 'finance/payment_history.html', context)

@login_required(login_url='/admin/login/')
def verify_payment(request, payment_id, action):
    """
    Logika Verifikasi (Approve/Reject) FR-03
    """
    payment = get_object_or_404(Payment, id=payment_id)
    invoice = payment.invoice

    if action == 'approve':
        # Update Invoice jadi LUNAS
        invoice.status = 'LUNAS'
        invoice.save()
        
        # Update Payment Info
        payment.verified_by = request.user
        payment.verified_at = timezone.now()
        payment.save()
        
        messages.success(request, f"Pembayaran {invoice.contract.tenant.full_name} disetujui.")

    elif action == 'reject':
        # Kembalikan status Invoice ke TELAT_BAYAR (agar ditagih ulang)
        invoice.status = 'TELAT_BAYAR'
        invoice.save()
        
        # Update Payment Info
        payment.verified_by = request.user
        payment.verified_at = timezone.now()
        payment.rejection_note = "Bukti tidak valid (Ditolak Admin)"
        payment.save()
        
        messages.error(request, f"Pembayaran {invoice.contract.tenant.full_name} DITOLAK.")

    return redirect('dashboard') # Kembali ke dashboard

@login_required(login_url='/accounts/login/')
def invoice_list(request):
    """
    Halaman Daftar Semua Tagihan (Admin)
    """
    # Ambil parameter filter dari URL
    status_filter = request.GET.get('status')
    search_query = request.GET.get('q')

    # Base Query: Urutkan dari yang terbaru (Jatuh tempo desc)
    invoices = Invoice.objects.all().order_by('-due_date')

    # 1. Filter by Status (jika ada)
    if status_filter:
        invoices = invoices.filter(status=status_filter)

    # 2. Search by Nama Penghuni / No Kamar
    if search_query:
        invoices = invoices.filter(
            Q(contract__tenant__full_name__icontains=search_query) |
            Q(contract__room__room_number__icontains=search_query)
        )

    context = {
        'invoices': invoices,
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
    costs = OperationCost.objects.all().order_by('-incurred_date')

    # Filter Lokasi (Security: Admin Ancol cuma lihat Ancol)
    if not request.user.is_superuser:
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            costs = costs.filter(kost_location=request.user.admin_profile.assigned_location)
        else:
            costs = costs.none()

    # Hitung Total Pengeluaran (Bulan Ini) - Opsional, buat total semua dulu
    total_expenses = costs.aggregate(Sum('amount'))['amount__sum'] or 0

    context = {
        'costs': costs,
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
        # Jika admin biasa, sembunyikan pilihan lokasi (auto-select)
        if not request.user.is_superuser and hasattr(request.user, 'admin_profile'):
            # (Opsional: logic untuk hide field lokasi bisa di form, tapi biarkan dulu agar simpel)
            pass

    return render(request, 'finance/operation_form.html', {'form': form, 'title': 'Catat Pengeluaran'})

@login_required(login_url='/accounts/login/')
def print_receipt(request, pk):
    """
    Halaman Cetak Kwitansi (Hanya untuk yang LUNAS)
    """
    invoice = get_object_or_404(Invoice, pk=pk)
    
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

    return render(request, 'finance/report_list.html', {
        'tickets': tickets, 
        'contract': contract,
        'hide_sidebar': True
    })
    
@login_required(login_url='/accounts/login/')
def admin_ticket_list(request):
    """
    Daftar Semua Laporan Kerusakan (Admin)
    """
    tickets = MaintenanceTicket.objects.all().order_by('-created_at')

    # Security: Filter Lokasi
    if not request.user.is_superuser:
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            tickets = tickets.filter(contract__room__kost_location=request.user.admin_profile.assigned_location)
        else:
            tickets = tickets.none()

    # Filter Status (Opsional, via URL ?status=PENDING)
    status_filter = request.GET.get('status')
    if status_filter:
        tickets = tickets.filter(status=status_filter)

    return render(request, 'finance/ticket_list.html', {
        'tickets': tickets,
        'current_status': status_filter
    })

@login_required(login_url='/accounts/login/')
def admin_ticket_update(request, pk):
    """
    Halaman Detail & Update Status Tiket
    """
    ticket = get_object_or_404(MaintenanceTicket, pk=pk)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status:
            ticket.status = new_status
            ticket.save()
            messages.success(request, f"Status laporan '{ticket.title}' berhasil diperbarui.")
            return redirect('ticket_list')

    return render(request, 'finance/ticket_detail.html', {'ticket': ticket})