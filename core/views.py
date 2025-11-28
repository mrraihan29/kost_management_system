from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from finance.models import Invoice, Payment
from tenants.models import TenantContract
from core.models import Room, KostLocation
from django.db.models import Sum

@login_required(login_url='/accounts/login/')
def admin_dashboard(request):
    """
    Dashboard Utama Admin Kost (FR-09, 10, 11)
    """
    # --- 1. FILTER LOKASI ---
    invoices = Invoice.objects.all()
    rooms = Room.objects.all().order_by('room_number') # Default ambil semua kamar
    
    if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
        user_location = request.user.admin_profile.assigned_location
        invoices = invoices.filter(contract__room__kost_location=user_location)
        rooms = rooms.filter(kost_location=user_location) # Filter kamar juga
        location_name = user_location.name
    else:
        location_name = "Semua Lokasi (Super Admin)"

    # --- 2. HITUNG KPI ---
    total_pending = invoices.filter(status='MENUNGGU_VERIFIKASI').count()
    total_overdue = invoices.filter(status='TELAT_BAYAR').count()
    income_this_month = invoices.filter(status='LUNAS').aggregate(Sum('total_amount'))['total_amount__sum'] or 0

    # --- 3. DATA PETA VISUAL KAMAR (FR-10) ---
    # Kita butuh list dictionary agar mudah di-loop di template
    room_visual_data = []
    
    for room in rooms:
        # Cek kontrak aktif di kamar ini
        active_contract = TenantContract.objects.filter(room=room, is_active=True).first()
        
        status_code = 'KOSONG'
        color_class = 'bg-light text-muted border' # Abu-abu (Default Kosong)
        tenant_name = 'Kosong'
        
        if active_contract:
            tenant_name = active_contract.tenant.full_name
            # Cek tagihan terakhir
            last_invoice = Invoice.objects.filter(contract=active_contract).order_by('-due_date').first()
            
            if last_invoice:
                if last_invoice.status == 'LUNAS':
                    status_code = 'LUNAS'
                    color_class = 'bg-success text-white' # Hijau
                elif last_invoice.status == 'TELAT_BAYAR':
                    status_code = 'TELAT'
                    color_class = 'bg-danger text-white' # Merah
                elif last_invoice.status == 'MENUNGGU_VERIFIKASI':
                    status_code = 'PROSES'
                    color_class = 'bg-warning text-dark' # Kuning
                else:
                    status_code = 'TAGIHAN'
                    color_class = 'bg-white border border-secondary text-dark' # Putih (Belum Lunas tapi belum telat)
            else:
                # Ada kontrak tapi belum ada tagihan (Baru masuk)
                status_code = 'AMAN'
                color_class = 'bg-success text-white'

        room_visual_data.append({
            'number': room.room_number,
            'tenant': tenant_name,
            'status': status_code,
            'color': color_class,
            'id': active_contract.id if active_contract else None
        })

    # --- 4. TABEL PERHATIAN ---
    attention_list = invoices.filter(
        status__in=['MENUNGGU_VERIFIKASI', 'TELAT_BAYAR']
    ).order_by('status', 'due_date')

    context = {
        'location_name': location_name,
        'total_pending': total_pending,
        'total_overdue': total_overdue,
        'income_this_month': income_this_month,
        'attention_list': attention_list,
        'room_visual_data': room_visual_data, # Data baru dikirim ke template
    }
    return render(request, 'core/dashboard.html', context)

def home(request):
    """
    Landing Page (Halaman Depan)
    """
    # Jika user sudah login sebagai admin, langsung ke dashboard saja
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    return render(request, 'home.html')