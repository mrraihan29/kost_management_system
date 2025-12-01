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
import csv
import datetime
from django.http import HttpResponse
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth
import openpyxl # Library Excel
from openpyxl.styles import Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from .forms import ReportFilterForm # Import form baru
from dateutil.relativedelta import relativedelta # Pastikan ini ada
from django.utils import timezone
from tenants.models import TenantContract

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
    Halaman Daftar Semua Tagihan (Admin) - FIXED SECURITY
    """
    status_filter = request.GET.get('status')
    search_query = request.GET.get('q')

    # 1. Base Query
    invoices = Invoice.objects.all().order_by('-due_date')

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
    Daftar Laporan Kerusakan (Dengan Filter Status & Kamar)
    """
    # 1. Base Query
    tickets = MaintenanceTicket.objects.all().order_by('-created_at')
    
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

    context = {
        'tickets': tickets,
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

    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status:
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
    
    invoices = Invoice.objects.filter(billing_period_start__year=year, status='LUNAS')
    costs = OperationCost.objects.filter(incurred_date__year=year)
    
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
        created_count = 0
        skipped_count = 0

        for contract in active_contracts:
            # Sesuaikan tanggal mulai tagihan dengan tanggal masuk penghuni
            # Contoh: Masuk tgl 15, maka periode mulai tgl 15 bulan depan
            try:
                billing_start = billing_start_base.replace(day=contract.start_date.day)
            except ValueError:
                # Fallback untuk tanggal 31 di bulan Februari, dll.
                billing_start = billing_start_base.replace(day=28)
            
            # Jatuh tempo H+10
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