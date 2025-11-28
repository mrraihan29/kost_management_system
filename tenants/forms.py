from django import forms
from .models import Tenant

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