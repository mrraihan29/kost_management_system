from django import forms
from .models import Tenant
from .models import TenantContract
from core.models import Room
class TenantForm(forms.ModelForm):
    class Meta:
        model = Tenant
        fields = ['full_name', 'phone_number', 'emergency_contact_phone', 'ktp_photo']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control-clean', 'placeholder': 'Nama Lengkap'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control-clean', 'placeholder': '08xxxxxxxx'}),
            'emergency_contact_phone': forms.TextInput(attrs={'class': 'form-control-clean', 'placeholder': 'Nomor Kontak Darurat'}),
            'ktp_photo': forms.FileInput(attrs={'class': 'form-control-clean'}),
        }
        labels = {
            'full_name': 'Nama Lengkap',
            'phone_number': 'Nomor HP',
            'emergency_contact_phone': 'Kontak Darurat',
            'ktp_photo': 'Foto KTP (Opsional)',
        }
        
class TenantContractForm(forms.ModelForm):
    """
    Form Assign Kamar (Buat Kontrak)
    """
    class Meta:
        model = TenantContract
        fields = ['room', 'start_date', 'monthly_rent_amount']
        widgets = {
            'start_date': forms.DateInput(attrs={'class': 'form-control-clean', 'type': 'date'}),
            'monthly_rent_amount': forms.NumberInput(attrs={'class': 'form-control-clean'}),
            'room': forms.Select(attrs={'class': 'form-select shadow-none border-secondary'}),
        }
        labels = {
            'room': 'Pilih Kamar Kosong',
            'start_date': 'Tanggal Mulai Sewa',
            'monthly_rent_amount': 'Harga Sewa (Deal)',
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None) # Terima user untuk filter lokasi
        super().__init__(*args, **kwargs)
        
        # Logika Filter Kamar Kosong
        # 1. Ambil semua kamar di lokasi admin tersebut
        rooms_query = Room.objects.all().order_by('room_number')
        
        if user and not user.is_superuser:
            if hasattr(user, 'admin_profile') and user.admin_profile.assigned_location:
                rooms_query = rooms_query.filter(kost_location=user.admin_profile.assigned_location)
        
        # 2. Filter hanya yang TIDAK punya kontrak aktif
        # (Exclude kamar yang ID-nya ada di daftar kontrak aktif)
        occupied_room_ids = TenantContract.objects.filter(is_active=True).values_list('room_id', flat=True)
        self.fields['room'].queryset = rooms_query.exclude(id__in=occupied_room_ids)