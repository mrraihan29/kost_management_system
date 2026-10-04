from django import forms
from django.core.exceptions import ValidationError
from core.models import KostLocation
from .models import Payment, ElectricityReading, OperationCost
from tenants.models import MaintenanceTicket
import datetime


# D-CODE-03: File validation for uploads
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp']
ALLOWED_FILE_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS + ['pdf']


def validate_file_size(value):
    """Validate that uploaded file is not larger than 5MB."""
    if value.size > MAX_UPLOAD_SIZE:
        raise ValidationError(f'File terlalu besar ({value.size // (1024*1024)}MB). Maksimal 5MB.')


def validate_image_file(value):
    """Validate image file: size + extension."""
    validate_file_size(value)
    ext = value.name.rsplit('.', 1)[-1].lower() if '.' in value.name else ''
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(f'Format file tidak didukung ({ext}). Gunakan: {", ".join(ALLOWED_IMAGE_EXTENSIONS)}')


def validate_proof_file(value):
    """Validate proof file: size + extension (images + PDF)."""
    validate_file_size(value)
    ext = value.name.rsplit('.', 1)[-1].lower() if '.' in value.name else ''
    if ext not in ALLOWED_FILE_EXTENSIONS:
        raise ValidationError(f'Format file tidak didukung ({ext}). Gunakan: {", ".join(ALLOWED_FILE_EXTENSIONS)}')
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

    def clean_payment_proof_file(self):
        f = self.cleaned_data.get('payment_proof_file')
        if f:
            validate_image_file(f)
        return f

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

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('meter_reading_start')
        end = cleaned_data.get('meter_reading_end')
        if start is not None and end is not None and end < start:
            raise ValidationError('Meteran Akhir tidak boleh lebih kecil dari Meteran Awal. Periksa kembali input Anda.')
        return cleaned_data

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

    def clean_proof_file(self):
        f = self.cleaned_data.get('proof_file')
        if f:
            validate_proof_file(f)
        return f
        
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
            'photo': 'Foto Kerusakan (Opsional)',
        }

    def clean_photo(self):
        f = self.cleaned_data.get('photo')
        if f:
            validate_image_file(f)
        return f
        
class ReportFilterForm(forms.Form):
    year = forms.ChoiceField(choices=[], label="Tahun", widget=forms.Select(attrs={'class': 'form-select shadow-none border-secondary'}))
    
    kost_location = forms.ModelChoiceField(
        queryset=KostLocation.objects.all(), 
        required=False, 
        label="Filter Lokasi (Opsional)",
        empty_label="-- Semua Lokasi --",
        widget=forms.Select(attrs={'class': 'form-select shadow-none border-secondary'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_year = datetime.datetime.now().year
        self.fields['year'].choices = [(r, str(r)) for r in range(current_year, current_year - 5, -1)]