from django import forms

from .models import KostLocation, Room


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


class RoomForm(forms.ModelForm):
    """
    Form Kelola Kamar (B-CRUD-04)
    """
    class Meta:
        model = Room
        fields = ['kost_location', 'room_number', 'price_monthly', 'is_token_electricity', 'capacity']
        widgets = {
            'kost_location': forms.Select(attrs={'class': 'form-select shadow-none border-secondary'}),
            'room_number': forms.TextInput(attrs={'class': 'form-control-clean', 'placeholder': 'Contoh: A-101'}),
            'price_monthly': forms.NumberInput(attrs={'class': 'form-control-clean', 'placeholder': 'Contoh: 1500000'}),
            'is_token_electricity': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control-clean', 'placeholder': '1'}),
        }
        labels = {
            'kost_location': 'Lokasi Kost',
            'room_number': 'Nomor Kamar',
            'price_monthly': 'Harga Sewa Bulanan (Rp)',
            'is_token_electricity': 'Listrik Token (Prabayar)',
            'capacity': 'Kapasitas (Orang)',
        }