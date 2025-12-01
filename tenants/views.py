from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.contrib import messages
from .models import Tenant

from django.urls import reverse_lazy
from django.views.generic.edit import CreateView, UpdateView
from django.contrib.messages.views import SuccessMessageMixin
from .forms import TenantForm
from django.utils import timezone
from .models import TenantContract
from .forms import TenantContractForm, TenantForm

@login_required(login_url='/accounts/login/')
def tenant_list(request):
    """
    Halaman Daftar Penghuni (Dengan Filter Keamanan Lokasi)
    """
    query = request.GET.get('q')
    
    # 1. Mulai dengan mengambil semua data
    tenants = Tenant.objects.all().order_by('-created_at')

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

    # 3. Filter Pencarian (tetap sama)
    if query:
        tenants = tenants.filter(
            Q(full_name__icontains=query) | 
            Q(phone_number__icontains=query)
        )
    
    total_tenants = tenants.count()
    # Hitung aktif berdasarkan filter lokasi di atas
    active_tenants = tenants.filter(contracts__is_active=True).distinct().count()

    context = {
        'tenants': tenants,
        'total_tenants': total_tenants,
        'active_tenants': active_tenants,
        'search_query': query
    }
    return render(request, 'tenants/tenant_list.html', context)

class TenantCreateView(SuccessMessageMixin, CreateView):
    model = Tenant
    form_class = TenantForm
    template_name = 'tenants/tenant_form.html'
    success_url = reverse_lazy('tenant_list') # Kembali ke list setelah sukses
    success_message = "Data penghuni berhasil ditambahkan"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Tambah Penghuni'
        context['btn_text'] = 'Simpan Data'
        return context

class TenantUpdateView(SuccessMessageMixin, UpdateView):
    model = Tenant
    form_class = TenantForm
    template_name = 'tenants/tenant_form.html'
    success_url = reverse_lazy('tenant_list')
    success_message = "Data penghuni berhasil diperbarui"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Penghuni'
        context['btn_text'] = 'Update Data'
        return context
    
@login_required(login_url='/accounts/login/')
def tenant_checkout(request, pk):
    """
    Aksi Check-Out: Menonaktifkan kontrak sewa penghuni
    """
    tenant = get_object_or_404(Tenant, pk=pk)
    
    # Cari kontrak yang masih aktif
    active_contract = tenant.contracts.filter(is_active=True).first()
    
    if active_contract:
        # 1. Nonaktifkan Kontrak
        active_contract.is_active = False
        # 2. Catat tanggal keluar (Hari ini)
        active_contract.end_date = timezone.now().date()
        active_contract.save()
        
        messages.success(request, f"Penghuni {tenant.full_name} berhasil di-Check Out. Kamar sekarang kosong.")
    else:
        messages.warning(request, "Penghuni ini tidak memiliki kontrak aktif.")
        
    return redirect('tenant_list')

class TenantContractCreateView(SuccessMessageMixin, CreateView):
    model = TenantContract
    form_class = TenantContractForm
    template_name = 'tenants/assign_room.html'
    success_url = reverse_lazy('tenant_list')
    success_message = "Berhasil assign kamar ke penghuni!"

    def get_form_kwargs(self):
        """Kirim user ke form agar bisa filter lokasi"""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        # Otomatis isi tenant berdasarkan URL (pk)
        tenant_id = self.kwargs['pk']
        form.instance.tenant = get_object_or_404(Tenant, pk=tenant_id)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tenant = get_object_or_404(Tenant, pk=self.kwargs['pk'])
        context['tenant'] = tenant
        return context