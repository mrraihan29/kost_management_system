from django import forms
from .models import KostLocation

class KostLocationForm(forms.ModelForm):
    """
    Form Pengaturan Lokasi & Tarif
    """
    class Meta:
        model = KostLocation
        fields = ['name', 'address', 'electricity_rate_per_kwh', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control-clean'}),
            'address': forms.Textarea(attrs={'class': 'form-control-clean', 'rows': 3}),
            'electricity_rate_per_kwh': forms.NumberInput(attrs={'class': 'form-control-clean'}),
            'description': forms.Textarea(attrs={'class': 'form-control-clean', 'rows': 3}),
        }
        labels = {
            'name': 'Nama Kost',
            'address': 'Alamat Lengkap',
            'electricity_rate_per_kwh': 'Tarif Listrik per KWH (Rp)',
            'description': 'Deskripsi / Catatan Tambahan',
        }