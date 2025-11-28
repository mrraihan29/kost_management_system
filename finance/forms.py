from django import forms
from core.models import KostLocation
from .models import Payment, ElectricityReading, OperationCost
from tenants.models import MaintenanceTicket
class PinValidationForm(forms.Form):
    """
    Formulir Langkah 1: Validasi Penghuni
    """
    # Dropdown pilih lokasi
    kost_location = forms.ModelChoiceField(
        queryset=KostLocation.objects.all(),
        label="Lokasi Kost",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    # Input text biasa untuk nomor kamar (agar fleksibel)
    room_number = forms.CharField(
        max_length=20, 
        label="Nomor Kamar",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contoh: A-101'})
    )
    
    # Input PIN (type password agar titik-titik)
    pin = forms.CharField(
        max_length=6, 
        label="PIN Pembayaran",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': '6 Digit PIN'})
    )

class PaymentUploadForm(forms.ModelForm):
    """
    Formulir Langkah 2: Upload Bukti
    """
    class Meta:
        model = Payment
        fields = ['payment_proof_file']
        widgets = {
            'payment_proof_file': forms.FileInput(attrs={'class': 'form-control'})
        }

class ElectricityForm(forms.ModelForm):
    """
    Form Input Listrik Manual (FR-06)
    """
    class Meta:
        model = ElectricityReading
        fields = ['meter_reading_start', 'meter_reading_end', 'rate_per_kwh']
        widgets = {
            'meter_reading_start': forms.NumberInput(attrs={'class': 'form-control-clean', 'placeholder': '0'}),
            'meter_reading_end': forms.NumberInput(attrs={'class': 'form-control-clean', 'placeholder': '0'}),
            'rate_per_kwh': forms.NumberInput(attrs={'class': 'form-control-clean', 'placeholder': '1500'}),
        }
        labels = {
            'meter_reading_start': 'Meteran Awal (KWH)',
            'meter_reading_end': 'Meteran Akhir (KWH)',
            'rate_per_kwh': 'Tarif per KWH (Rp)',
        }

class OperationCostForm(forms.ModelForm):
    """
    Form Pencatatan Biaya Operasional (FR-07)
    """
    class Meta:
        model = OperationCost
        fields = ['kost_location', 'category', 'amount', 'incurred_date', 'description', 'proof_file']
        widgets = {
            'kost_location': forms.Select(attrs={'class': 'form-select shadow-none border-secondary'}),
            'category': forms.Select(attrs={'class': 'form-select shadow-none border-secondary'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control-clean', 'placeholder': 'Contoh: 50000'}),
            'incurred_date': forms.DateInput(attrs={'class': 'form-control-clean', 'type': 'date'}),
            'description': forms.Textarea(attrs={'class': 'form-control-clean', 'rows': 3, 'placeholder': 'Keterangan pengeluaran...'}),
            'proof_file': forms.FileInput(attrs={'class': 'form-control-clean'}),
        }
        labels = {
            'kost_location': 'Lokasi Kost',
            'category': 'Kategori Biaya',
            'amount': 'Jumlah (Rp)',
            'incurred_date': 'Tanggal Pengeluaran',
            'description': 'Keterangan',
            'proof_file': 'Foto Nota / Bukti',
        }
        
class MaintenanceForm(forms.ModelForm):
    class Meta:
        model = MaintenanceTicket
        fields = ['title', 'priority', 'description', 'photo']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control-clean', 'placeholder': 'Contoh: Kran Air Bocor'}),
            'priority': forms.Select(attrs={'class': 'form-select shadow-none border-secondary'}),
            'description': forms.Textarea(attrs={'class': 'form-control-clean', 'rows': 4, 'placeholder': 'Jelaskan kerusakan secara detail...'}),
            'photo': forms.FileInput(attrs={'class': 'form-control-clean'}),
        }
        labels = {
            'title': 'Judul Masalah',
            'priority': 'Tingkat Urgensi',
            'description': 'Keterangan',
            'photo': 'Foto Kerusakan (Wajib)',
        }