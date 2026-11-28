from typing import cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.http import Http404, HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic.edit import CreateView, UpdateView

from config.security import log_action
from core.scoping import NoLocation, get_scoped_or_404, location_for, scoped
from finance.models import Invoice
from users.models import User

from .forms import TenantContractForm, TenantForm
from .models import Tenant, TenantContract


class StaffWithLocationRequiredMixin(UserPassesTestMixin):
    """Hanya Owner atau Staff dengan lokasi yang boleh mengakses."""

    request: HttpRequest

    def test_func(self):
        try:
            location_for(cast(User, self.request.user))
            return True
        except NoLocation:
            return False

    def handle_no_permission(self):
        messages.error(self.request, "Akses ditolak. Hanya admin/staff yang ditugaskan lokasi.")
        return redirect("dashboard")


@login_required(login_url="/accounts/login/")
def tenant_list(request):
    """
    Halaman Daftar Penghuni (Dengan Filter Keamanan Lokasi)
    """
    query = request.GET.get("q")

    # 1. Mulai dengan mengambil semua data (C-PERF-04 fix: prefetch contracts)
    tenants = Tenant.objects.prefetch_related(
        Prefetch(
            "contracts",
            queryset=TenantContract.objects.select_related("room__kost_location").order_by(
                "-start_date"
            ),
        )
    ).order_by("-created_at")

    # 2. CEK HAK AKSES
    tenants = scoped(tenants, request.user, "contracts__room__kost_location").distinct()

    # Hitung KPI sebelum filter pencarian agar angka tetap konstan
    total_tenants = tenants.count()
    active_tenants = tenants.filter(contracts__is_active=True).distinct().count()

    # 3. Filter Pencarian (setelah KPI dihitung)
    if query:
        tenants = tenants.filter(Q(full_name__icontains=query) | Q(phone_number__icontains=query))

    # C-PAGE-01: Pagination
    paginator = Paginator(tenants, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "tenants": page_obj,
        "page_obj": page_obj,
        "total_tenants": total_tenants,
        "active_tenants": active_tenants,
        "search_query": query,
    }
    return render(request, "tenants/tenant_list.html", context)


class TenantCreateView(
    LoginRequiredMixin, StaffWithLocationRequiredMixin, SuccessMessageMixin, CreateView
):
    model = Tenant
    form_class = TenantForm
    template_name = "tenants/tenant_form.html"
    success_url = reverse_lazy("tenant_list")  # Kembali ke list setelah sukses
    success_message = "Data penghuni berhasil ditambahkan"
    login_url = "/accounts/login/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Tambah Penghuni"
        context["btn_text"] = "Simpan Data"
        return context


class TenantUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Tenant
    form_class = TenantForm
    template_name = "tenants/tenant_form.html"
    success_url = reverse_lazy("tenant_list")
    success_message = "Data penghuni berhasil diperbarui"
    login_url = "/accounts/login/"

    def get_queryset(self):
        """W9/BQ-7: admin biasa hanya bisa edit tenant dengan kontrak AKTIF di lokasinya.
        Tenant historis (tanpa kontrak aktif) tetap terlihat di list, tapi read-only."""
        qs = super().get_queryset()
        try:
            location = location_for(cast(User, self.request.user))
        except NoLocation:
            return qs.none()
        if location is not None:
            return qs.filter(
                contracts__room__kost_location=location,
                contracts__is_active=True,
            ).distinct()
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Edit Penghuni"
        context["btn_text"] = "Update Data"
        return context


@require_POST
@login_required(login_url="/accounts/login/")
def tenant_checkout(request, pk):
    """
    Aksi Check-Out: Menonaktifkan kontrak sewa penghuni
    """
    tenant = get_scoped_or_404(
        Tenant.objects.all(), request.user, "contracts__room__kost_location", pk=pk
    )

    # Cari kontrak yang masih aktif
    active_contract = tenant.contracts.filter(is_active=True).first()

    if active_contract:
        # B-FLOW-01 fix: Cek apakah ada tagihan belum lunas sebelum checkout
        unpaid_invoices = Invoice.objects.filter(
            contract=active_contract,
            status__in=["BELUM_LUNAS", "TELAT_BAYAR", "MENUNGGU_VERIFIKASI"],
        ).exists()
        if unpaid_invoices:
            messages.warning(
                request, f"Tidak bisa checkout {tenant.full_name}. Masih ada tagihan belum lunas."
            )
            return redirect("tenant_list")

        # 1. Nonaktifkan Kontrak
        active_contract.is_active = False
        # 2. Catat tanggal keluar (RC4: pakai localdate sesuai TIME_ZONE bisnis)
        active_contract.end_date = timezone.localdate()
        active_contract.save()

        # SEC-12: Audit log checkout
        log_action(
            request,
            "TENANT_CHECKOUT",
            f"Tenant #{tenant.pk}",
            f"Name: {tenant.full_name}, Room: {active_contract.room.room_number}",
        )

        messages.success(
            request, f"Penghuni {tenant.full_name} berhasil di-Check Out. Kamar sekarang kosong."
        )
    else:
        messages.warning(request, "Penghuni ini tidak memiliki kontrak aktif.")

    return redirect("tenant_list")


@require_POST
@login_required(login_url="/accounts/login/")
def tenant_delete(request, pk):
    """
    Hapus Data Penghuni (B-CRUD-01)
    Hanya bisa jika tidak punya kontrak aktif dan tidak ada invoice unpaid
    """
    tenant = get_scoped_or_404(
        Tenant.objects.all(), request.user, "contracts__room__kost_location", pk=pk
    )

    # Cek apakah punya kontrak aktif
    if tenant.contracts.filter(is_active=True).exists():
        messages.error(
            request,
            f"Tidak bisa menghapus {tenant.full_name}. Masih ada kontrak aktif. Checkout dulu.",
        )
        return redirect("tenant_list")

    # Cek apakah ada invoice yang belum lunas
    unpaid = Invoice.objects.filter(
        contract__tenant=tenant, status__in=["BELUM_LUNAS", "TELAT_BAYAR", "MENUNGGU_VERIFIKASI"]
    ).exists()
    if unpaid:
        messages.error(
            request, f"Tidak bisa menghapus {tenant.full_name}. Masih ada tagihan belum lunas."
        )
        return redirect("tenant_list")

    tenant_name = tenant.full_name
    tenant.delete()
    # SEC-12: Audit log deletion
    log_action(request, "TENANT_DELETED", f"Tenant #{pk}", f"Name: {tenant_name}")
    messages.success(request, f"Data penghuni '{tenant_name}' berhasil dihapus.")
    return redirect("tenant_list")


class TenantContractCreateView(
    LoginRequiredMixin, StaffWithLocationRequiredMixin, SuccessMessageMixin, CreateView
):
    model = TenantContract
    form_class = TenantContractForm
    template_name = "tenants/assign_room.html"
    success_url = reverse_lazy("tenant_list")
    success_message = "Berhasil assign kamar ke penghuni!"
    login_url = "/accounts/login/"

    def get_form_kwargs(self):
        """Kirim user ke form agar bisa filter lokasi"""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_tenant(self):
        """RC2/BQ-7: scope tenant sebelum render/POST — 404 untuk tenant asing.

        Visible: fresh (tanpa kontrak) atau punya riwayat/aktif di lokasi staff.
        PG-1: pemindahan tenant yang hanya punya histori di lokasi lain diblokir
        sampai product owner memutuskan siapa yang boleh memulai.
        """
        tenant = get_object_or_404(Tenant, pk=self.kwargs["pk"])
        try:
            location = location_for(cast(User, self.request.user))
        except NoLocation as exc:
            raise Http404("Tenant tidak ditemukan.") from exc
        if location is not None:
            has_contracts = tenant.contracts.exists()
            has_own_history = tenant.contracts.filter(room__kost_location=location).exists()
            if has_contracts and not has_own_history:
                raise Http404("Tenant tidak ditemukan.")
        return tenant

    def form_valid(self, form):
        # Otomatis isi tenant berdasarkan URL (pk) — scope dulu (RC2)
        tenant = self.get_tenant()

        # B-FLOW-02 fix: Cegah double assignment
        if tenant.contracts.filter(is_active=True).exists():
            messages.error(
                self.request,
                f"{tenant.full_name} sudah memiliki kontrak aktif. Checkout dulu sebelum assign kamar baru.",
            )
            return redirect("tenant_list")

        cast(TenantContractForm, form).instance.tenant = tenant
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tenant"] = self.get_tenant()  # RC2: authorize BEFORE rendering
        return context
