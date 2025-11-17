from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from core.models import Room
from tenants.models import TenantContract
from .models import Invoice, Payment
from .forms import PinValidationForm, PaymentUploadForm
from django.contrib.auth.decorators import login_required
from django.utils import timezone

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