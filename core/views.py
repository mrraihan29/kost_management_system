from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from finance.models import Invoice, Payment
from tenants.models import TenantContract
from core.models import Room, KostLocation
from django.db.models import Sum
from .forms import KostLocationForm
from django.contrib import messages
# --- VIEW 1: LANDING PAGE (YANG HILANG) ---
def home(request):
    """
    Landing Page (Halaman Depan)
    """
    # Jika user sudah login sebagai admin, langsung ke dashboard saja
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    return render(request, 'home.html')

# --- VIEW 2: DASHBOARD ADMIN ---
@login_required(login_url='/accounts/login/')
def admin_dashboard(request):
    """
    Dashboard Utama (Dengan Filter Superuser & Peta Visual)
    """
    # Base Query
    invoices = Invoice.objects.all()
    rooms = Room.objects.all().order_by('room_number')
    
    # Data untuk Dropdown Filter (Hanya Superuser butuh ini)
    all_locations = KostLocation.objects.all() if request.user.is_superuser else None
    selected_location_id = request.GET.get('location') # Ambil dari URL ?location=1

    # --- LOGIKA FILTER UTAMA ---
    if not request.user.is_superuser:
        # KONDISI 1: ADMIN BIASA (Dipaksa ke lokasinya)
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            user_location = request.user.admin_profile.assigned_location
            invoices = invoices.filter(contract__room__kost_location=user_location)
            rooms = rooms.filter(kost_location=user_location)
            location_name = user_location.name
        else:
            invoices = invoices.none()
            rooms = rooms.none()
            location_name = "Tidak Ada Lokasi"
    
    else:
        # KONDISI 2: SUPERUSER
        if selected_location_id and selected_location_id != "":
            # Jika Superuser MEMILIH lokasi tertentu
            try:
                location_obj = KostLocation.objects.get(id=selected_location_id)
                invoices = invoices.filter(contract__room__kost_location=location_obj)
                rooms = rooms.filter(kost_location=location_obj)
                location_name = f"Lokasi: {location_obj.name}"
            except KostLocation.DoesNotExist:
                location_name = "Semua Lokasi (Error ID)"
        else:
            # Default: Lihat Semua
            location_name = "Semua Lokasi (Global)"

    # --- HITUNG KPI (Otomatis menyesuaikan filter di atas) ---
    total_pending = invoices.filter(status='MENUNGGU_VERIFIKASI').count()
    total_overdue = invoices.filter(status='TELAT_BAYAR').count()
    income_this_month = invoices.filter(status='LUNAS').aggregate(Sum('total_amount'))['total_amount__sum'] or 0

    # --- DATA PETA VISUAL (FR-10) ---
    room_visual_data = []
    for room in rooms:
        active_contract = room.contracts.filter(is_active=True).first()
        status_code = 'KOSONG'
        color_class = 'bg-light text-muted border'
        tenant_name = 'Kosong'
        
        if active_contract:
            tenant_name = active_contract.tenant.full_name
            last_invoice = active_contract.invoices.order_by('-due_date').first()
            if last_invoice:
                if last_invoice.status == 'LUNAS':
                    status_code = 'LUNAS'; color_class = 'bg-success text-white'
                elif last_invoice.status == 'TELAT_BAYAR':
                    status_code = 'TELAT'; color_class = 'bg-danger text-white'
                elif last_invoice.status == 'MENUNGGU_VERIFIKASI':
                    status_code = 'PROSES'; color_class = 'bg-warning text-dark'
                else:
                    status_code = 'TAGIHAN'; color_class = 'bg-white border border-secondary text-dark'
            else:
                status_code = 'AMAN'; color_class = 'bg-success text-white'

        room_visual_data.append({
            'number': room.room_number,
            'tenant': tenant_name,
            'status': status_code,
            'color': color_class,
        })

    # --- TABEL PERHATIAN ---
    attention_list = invoices.filter(
        status__in=['MENUNGGU_VERIFIKASI', 'TELAT_BAYAR']
    ).order_by('status', 'due_date')

    context = {
        'location_name': location_name,
        'total_pending': total_pending,
        'total_overdue': total_overdue,
        'income_this_month': income_this_month,
        'attention_list': attention_list,
        'room_visual_data': room_visual_data,
        'all_locations': all_locations, 
        'selected_location_id': int(selected_location_id) if selected_location_id else None
    }
    return render(request, 'core/dashboard.html', context)

@login_required(login_url='/accounts/login/')
def location_list(request):
    """
    Halaman Daftar Lokasi (Hanya untuk Superuser)
    """
    if not request.user.is_superuser:
        # Jika admin biasa coba akses list, lempar langsung ke edit punya dia
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            return redirect('location_update', pk=request.user.admin_profile.assigned_location.id)
        else:
            return redirect('dashboard') # Admin tanpa lokasi

    locations = KostLocation.objects.all()
    return render(request, 'core/location_list.html', {'locations': locations})

@login_required(login_url='/accounts/login/')
def location_update(request, pk):
    """
    Halaman Edit Lokasi & Tarif
    """
    location = get_object_or_404(KostLocation, pk=pk)

    # Security Check: Admin biasa dilarang edit lokasi orang lain
    if not request.user.is_superuser:
        if not hasattr(request.user, 'admin_profile') or request.user.admin_profile.assigned_location != location:
            messages.error(request, "Anda tidak memiliki akses untuk mengubah pengaturan lokasi ini.")
            return redirect('dashboard')

    if request.method == 'POST':
        form = KostLocationForm(request.POST, instance=location)
        if form.is_valid():
            form.save()
            messages.success(request, f"Pengaturan '{location.name}' berhasil diperbarui.")
            # Kembali ke halaman yang sesuai role
            if request.user.is_superuser:
                return redirect('location_list')
            return redirect('dashboard')
    else:
        form = KostLocationForm(instance=location)

    return render(request, 'core/location_form.html', {'form': form, 'location': location})