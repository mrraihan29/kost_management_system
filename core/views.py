from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from finance.models import Invoice, Payment
from finance.services import sync_overdue_invoice_statuses
from tenants.models import TenantContract
from core.models import Room, KostLocation
from django.db.models import Sum, Prefetch
from .forms import KostLocationForm, RoomForm
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_POST
import re
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
    sync_overdue_invoice_statuses()

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
            except (KostLocation.DoesNotExist, ValueError, TypeError):
                location_name = "Semua Lokasi (Error ID)"
        else:
            # Default: Lihat Semua
            location_name = "Semua Lokasi (Global)"

    # --- HITUNG KPI (Otomatis menyesuaikan filter di atas) ---
    total_pending = invoices.filter(status='MENUNGGU_VERIFIKASI').count()
    total_overdue = invoices.filter(status='TELAT_BAYAR').count()
    
    # A-DATA-02 fix: Filter pemasukan bulan ini berdasarkan bulan & tahun saat ini
    now = timezone.now()
    income_this_month = invoices.filter(
        status='LUNAS',
        billing_period_start__month=now.month,
        billing_period_start__year=now.year
    ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0

    # --- DATA PETA VISUAL (FR-10) ---
    # C-PERF-01 fix: Prefetch untuk menghindari N+1 queries
    rooms = rooms.select_related('kost_location').prefetch_related(
        Prefetch('contracts', queryset=TenantContract.objects.filter(is_active=True).select_related('tenant').prefetch_related(
            Prefetch('invoices', queryset=Invoice.objects.order_by('-due_date'))
        ))
    )
    
    room_visual_data = []
    for room in rooms:
        active_contract = room.contracts.all().first()  # Sudah di-prefetch, tidak query lagi
        status_code = 'KOSONG'
        color_class = 'bg-light text-muted border'
        tenant_name = 'Kosong'
        
        if active_contract:
            tenant_name = active_contract.tenant.full_name
            last_invoice = active_contract.invoices.all().first()  # Sudah di-prefetch
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
    ).select_related(
        'contract__tenant', 'contract__room__kost_location'
    ).order_by('status', 'due_date')

    try:
        selected_loc_int = int(selected_location_id) if selected_location_id else None
    except (ValueError, TypeError):
        selected_loc_int = None

    context = {
        'location_name': location_name,
        'total_pending': total_pending,
        'total_overdue': total_overdue,
        'income_this_month': income_this_month,
        'attention_list': attention_list,
        'room_visual_data': room_visual_data,
        'all_locations': all_locations, 
        'selected_location_id': selected_loc_int
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


# --- ROOM MANAGEMENT (B-CRUD-04) ---

@login_required(login_url='/accounts/login/')
def room_list(request):
    """
    Halaman Daftar Kamar (B-CRUD-04)
    """
    rooms = Room.objects.all().select_related('kost_location').order_by('kost_location__name', 'room_number')
    
    # Filter Lokasi (Security)
    if not request.user.is_superuser:
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            rooms = rooms.filter(kost_location=request.user.admin_profile.assigned_location)
        else:
            rooms = rooms.none()
    
    rooms = list(rooms)

    def room_sort_key(room):
        parts = re.split(r'(\d+)', (room.room_number or '').lower())
        key_parts = []
        for part in parts:
            if not part:
                continue
            if part.isdigit():
                key_parts.append((0, int(part)))
            else:
                key_parts.append((1, part))
        return key_parts

    rooms.sort(key=room_sort_key)

    # Tambahkan info okupansi ke setiap room
    for room in rooms:
        room.active_contract = room.contracts.filter(is_active=True).select_related('tenant').first()
    
    context = {
        'rooms': rooms,
        'total_rooms': len(rooms),
        'occupied_rooms': sum(1 for r in rooms if r.active_contract),
    }
    return render(request, 'core/room_list.html', context)

@login_required(login_url='/accounts/login/')
def room_create(request):
    """
    Form Tambah Kamar (B-CRUD-04)
    """
    if not request.user.is_superuser:
        if not request.user.is_staff:
            messages.error(request, "Akses ditolak. Hanya admin/staff yang dapat menambah kamar.")
            return redirect('dashboard')
        if not hasattr(request.user, 'admin_profile') or not request.user.admin_profile.assigned_location:
            messages.error(request, "Akses ditolak. Akun admin belum ditugaskan ke lokasi manapun.")
            return redirect('dashboard')

    if request.method == 'POST':
        form = RoomForm(request.POST)
        if form.is_valid():
            room = form.save(commit=False)
            # Security: Jika bukan superuser, paksa lokasi
            if not request.user.is_superuser and hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
                room.kost_location = request.user.admin_profile.assigned_location
            room.save()
            messages.success(request, f"Kamar {room.room_number} berhasil ditambahkan.")
            return redirect('room_list')
    else:
        form = RoomForm()
        # Pre-fill lokasi untuk admin biasa
        if not request.user.is_superuser and hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            form.fields['kost_location'].initial = request.user.admin_profile.assigned_location
            form.fields['kost_location'].queryset = KostLocation.objects.filter(pk=request.user.admin_profile.assigned_location.pk)
    
    return render(request, 'core/room_form.html', {'form': form, 'title': 'Tambah Kamar'})

@login_required(login_url='/accounts/login/')
def room_update(request, pk):
    """
    Edit Data Kamar (B-CRUD-04)
    """
    room = get_object_or_404(Room, pk=pk)
    
    # Security: Cek kepemilikan lokasi
    if not request.user.is_superuser:
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            if room.kost_location != request.user.admin_profile.assigned_location:
                messages.error(request, "Anda tidak memiliki akses ke kamar ini.")
                return redirect('room_list')
        else:
            return redirect('dashboard')
    
    if request.method == 'POST':
        form = RoomForm(request.POST, instance=room)
        if form.is_valid():
            updated_room = form.save(commit=False)
            if not request.user.is_superuser and hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
                updated_room.kost_location = request.user.admin_profile.assigned_location
            updated_room.save()
            messages.success(request, f"Kamar {room.room_number} berhasil diperbarui.")
            return redirect('room_list')
    else:
        form = RoomForm(instance=room)
        if not request.user.is_superuser and hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            form.fields['kost_location'].queryset = KostLocation.objects.filter(pk=request.user.admin_profile.assigned_location.pk)
    
    return render(request, 'core/room_form.html', {'form': form, 'title': f'Edit Kamar {room.room_number}'})

@require_POST
@login_required(login_url='/accounts/login/')
def room_delete(request, pk):
    """
    Hapus Kamar (B-CRUD-04) — Hanya jika tidak ada kontrak aktif
    """
    room = get_object_or_404(Room, pk=pk)
    
    # Security
    if not request.user.is_superuser:
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            if room.kost_location != request.user.admin_profile.assigned_location:
                messages.error(request, "Anda tidak memiliki akses ke kamar ini.")
                return redirect('room_list')
        else:
            return redirect('dashboard')
    
    # Cek apakah kamar sedang ditempati
    if room.contracts.filter(is_active=True).exists():
        messages.error(request, f"Kamar {room.room_number} tidak bisa dihapus karena masih ada penghuni aktif.")
        return redirect('room_list')
    
    room_number = room.room_number
    room.delete()
    messages.success(request, f"Kamar '{room_number}' berhasil dihapus.")
    return redirect('room_list')