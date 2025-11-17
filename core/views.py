from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from finance.models import Invoice, Payment
from tenants.models import TenantContract
from django.db.models import Sum

@login_required(login_url='/admin/login/') # Proteksi: Wajib Login
def admin_dashboard(request):
    """
    Dashboard Utama Admin Kost (FR-09, 11)
    """
    # --- 1. FILTER LOKASI (Multi-Tenancy sederhana) ---
    # Admin hanya melihat data sesuai lokasi yang ditugaskan di profilnya
    # (Asumsi: Superuser melihat semua, Admin biasa melihat lokasinya saja)
    
    # Default: Ambil semua (untuk Superuser)
    invoices = Invoice.objects.all()
    
    # Jika Admin biasa (punya profil), filter berdasarkan lokasi
    if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
        user_location = request.user.admin_profile.assigned_location
        # Filter invoice berdasarkan room -> location
        invoices = invoices.filter(contract__room__kost_location=user_location)
        location_name = user_location.name
    else:
        location_name = "Semua Lokasi (Super Admin)"

    # --- 2. HITUNG KPI (FR-09) ---
    total_pending = invoices.filter(status='MENUNGGU_VERIFIKASI').count()
    total_overdue = invoices.filter(status='TELAT_BAYAR').count()
    
    # Hitung uang masuk bulan ini (Simple version)
    income_this_month = invoices.filter(status='LUNAS').aggregate(Sum('total_amount'))['total_amount__sum'] or 0

    # --- 3. TABEL "PERLU PERHATIAN" (FR-11) ---
    # Ambil invoice yang butuh tindakan (Pending & Telat), urutkan yang pending dulu
    attention_list = invoices.filter(
        status__in=['MENUNGGU_VERIFIKASI', 'TELAT_BAYAR']
    ).order_by('status', 'due_date')  # 'M' abjadnya duluan dari 'T', jadi Pending muncul duluan

    context = {
        'location_name': location_name,
        'total_pending': total_pending,
        'total_overdue': total_overdue,
        'income_this_month': income_this_month,
        'attention_list': attention_list,
    }
    return render(request, 'core/dashboard.html', context)