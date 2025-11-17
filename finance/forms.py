from django import forms
from core.models import KostLocation
from .models import Payment

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