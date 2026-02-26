from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Prefetch
from django.contrib import messages
from .models import Tenant, TenantContract
from finance.models import Invoice
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.urls import reverse_lazy
from django.views.generic.edit import CreateView, UpdateView
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from .forms import TenantForm, TenantContractForm
from django.utils import timezone


class StaffWithLocationRequiredMixin(UserPassesTestMixin):
    """Hanya superuser atau staff dengan assigned_location yang boleh mengakses."""

    def test_func(self):
        user = self.request.user
        if user.is_superuser:
            return True
        return (
            user.is_staff
            and hasattr(user, 'admin_profile')
            and user.admin_profile.assigned_location is not None
        )

    def handle_no_permission(self):
        messages.error(self.request, "Akses ditolak. Hanya admin/staff yang ditugaskan lokasi.")
        return redirect('dashboard')

@login_required(login_url='/accounts/login/')
def tenant_list(request):
    """
    Halaman Daftar Penghuni (Dengan Filter Keamanan Lokasi)
    """
    query = request.GET.get('q')
    
    # 1. Mulai dengan mengambil semua data (C-PERF-04 fix: prefetch contracts)
    tenants = Tenant.objects.prefetch_related(
        Prefetch('contracts', queryset=TenantContract.objects.select_related('room__kost_location').order_by('-start_date'))
    ).order_by('-created_at')

    # 2. CEK HAK AKSES (Logic Baru)
    # Jika dia BUKAN Superuser, kita filter datanya
    if not request.user.is_superuser:
        # Cek apakah dia punya profil admin dan lokasi yang ditugaskan
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            user_location = request.user.admin_profile.assigned_location
            
            # Filter penghuni yang punya kontrak di lokasi admin tersebut
            # (Menggunakan lookup double underscore __)
            tenants = tenants.filter(contracts__room__kost_location=user_location).distinct()
        else:
            # Jika admin tidak punya lokasi (error akun), jangan tampilkan apa-apa
            tenants = tenants.none()

    # Hitung KPI sebelum filter pencarian agar angka tetap konstan
    total_tenants = tenants.count()
    active_tenants = tenants.filter(contracts__is_active=True).distinct().count()

    # 3. Filter Pencarian (setelah KPI dihitung)
    if query:
        tenants = tenants.filter(
            Q(full_name__icontains=query) | 
            Q(phone_number__icontains=query)
        )

    # C-PAGE-01: Pagination
    paginator = Paginator(tenants, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'tenants': page_obj,
        'page_obj': page_obj,
        'total_tenants': total_tenants,
        'active_tenants': active_tenants,
        'search_query': query
    }
    return render(request, 'tenants/tenant_list.html', context)

class TenantCreateView(LoginRequiredMixin, StaffWithLocationRequiredMixin, SuccessMessageMixin, CreateView):
    model = Tenant
    form_class = TenantForm
    template_name = 'tenants/tenant_form.html'
    success_url = reverse_lazy('tenant_list') # Kembali ke list setelah sukses
    success_message = "Data penghuni berhasil ditambahkan"
    login_url = '/accounts/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Tambah Penghuni'
        context['btn_text'] = 'Simpan Data'
        return context

class TenantUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Tenant
    form_class = TenantForm
    template_name = 'tenants/tenant_form.html'
    success_url = reverse_lazy('tenant_list')
    success_message = "Data penghuni berhasil diperbarui"
    login_url = '/accounts/login/'

    def get_queryset(self):
        """Security: Admin biasa hanya bisa edit tenant di lokasinya"""
        qs = super().get_queryset()
        if not self.request.user.is_superuser:
            if hasattr(self.request.user, 'admin_profile') and self.request.user.admin_profile.assigned_location:
                qs = qs.filter(contracts__room__kost_location=self.request.user.admin_profile.assigned_location).distinct()
            else:
                qs = qs.none()
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Penghuni'
        context['btn_text'] = 'Update Data'
        return context
    
@require_POST
@login_required(login_url='/accounts/login/')
def tenant_checkout(request, pk):
    """
    Aksi Check-Out: Menonaktifkan kontrak sewa penghuni
    """
    tenant = get_object_or_404(Tenant, pk=pk)
    
    # Cari kontrak yang masih aktif
    active_contract = tenant.contracts.filter(is_active=True).first()

    # Security: Cek kepemilikan lokasi
    if active_contract and not request.user.is_superuser:
        if hasattr(request.user, 'admin_profile') and request.user.admin_profile.assigned_location:
            if active_contract.room.kost_location != request.user.admin_profile.assigned_location:
                messages.error(request, "Anda tidak memiliki akses untuk checkout penghuni ini.")
                return redirect('tenant_list')
        else:
            messages.error(request, "Akun Anda belum ditugaskan ke lokasi manapun.")
            return redirect('tenant_list')
    
    if active_contract:
        # B-FLOW-01 fix: Cek apakah ada tagihan belum lunas sebelum checkout
        unpaid_invoices = Invoice.objects.filter(
            contract=active_contract,
            status__in=['BELUM_LUNAS', 'TELAT_BAYAR', 'MENUNGGU_VERIFIKASI']
        ).exists()
        if unpaid_invoices:
            messages.warning(request, f"Tidak bisa checkout {tenant.full_name}. Masih ada tagihan belum lunas.")
            return redirect('tenant_list')
        
        # 1. Nonaktifkan Kontrak
        active_contract.is_active = False
        # 2. Catat tanggal keluar (Hari ini)
        active_contract.end_date = timezone.now().date()
        active_contract.save()
        
        messages.success(request, f"Penghuni {tenant.full_name} berhasil di-Check Out. Kamar sekarang kosong.")
    else:
        messages.warning(request, "Penghuni ini tidak memiliki kontrak aktif.")
        
    return redirect('tenant_list')

@require_POST
@login_required(login_url='/accounts/login/')
def tenant_delete(request, pk):
    """
    Hapus Data Penghuni (B-CRUD-01)
    Hanya bisa jika tidak punya kontrak aktif dan tidak ada invoice unpaid
    """
    tenant = get_object_or_404(Tenant, pk=pk)
    
    # Cek apakah punya kontrak aktif
    if tenant.contracts.filter(is_active=True).exists():
        messages.error(request, f"Tidak bisa menghapus {tenant.full_name}. Masih ada kontrak aktif. Checkout dulu.")
        return redirect('tenant_list')
    
    # Cek apakah ada invoice yang belum lunas
    unpaid = Invoice.objects.filter(
        contract__tenant=tenant,
        status__in=['BELUM_LUNAS', 'TELAT_BAYAR', 'MENUNGGU_VERIFIKASI']
    ).exists()
    if unpaid:
        messages.error(request, f"Tidak bisa menghapus {tenant.full_name}. Masih ada tagihan belum lunas.")
        return redirect('tenant_list')
    
    tenant_name = tenant.full_name
    tenant.delete()
    messages.success(request, f"Data penghuni '{tenant_name}' berhasil dihapus.")
    return redirect('tenant_list')

class TenantContractCreateView(LoginRequiredMixin, StaffWithLocationRequiredMixin, SuccessMessageMixin, CreateView):
    model = TenantContract
    form_class = TenantContractForm
    template_name = 'tenants/assign_room.html'
    success_url = reverse_lazy('tenant_list')
    success_message = "Berhasil assign kamar ke penghuni!"
    login_url = '/accounts/login/'

    def get_form_kwargs(self):
        """Kirim user ke form agar bisa filter lokasi"""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        # Otomatis isi tenant berdasarkan URL (pk)
        tenant_id = self.kwargs['pk']
        tenant = get_object_or_404(Tenant, pk=tenant_id)
        
        # B-FLOW-02 fix: Cegah double assignment
        if tenant.contracts.filter(is_active=True).exists():
            messages.error(self.request, f"{tenant.full_name} sudah memiliki kontrak aktif. Checkout dulu sebelum assign kamar baru.")
            return redirect('tenant_list')
        
        form.instance.tenant = tenant
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tenant = get_object_or_404(Tenant, pk=self.kwargs['pk'])
        context['tenant'] = tenant
        return context