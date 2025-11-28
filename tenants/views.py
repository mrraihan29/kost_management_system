from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q  # Import Q untuk pencarian kompleks
from django.contrib import messages
from .models import Tenant

from django.urls import reverse_lazy
from django.views.generic.edit import CreateView, UpdateView
from django.contrib.messages.views import SuccessMessageMixin
from .forms import TenantForm

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