from django import forms
from django.contrib.auth.forms import UserCreationForm
from core.models import KostLocation
from .models import User

class StaffCreationForm(UserCreationForm):
    """
    Form untuk membuat Admin Kost Baru + Assign Lokasi
    """
    assigned_location = forms.ModelChoiceField(
        queryset=KostLocation.objects.all(),
        required=True,
        label="Tugaskan di Lokasi",
        widget=forms.Select(attrs={'class': 'form-select shadow-none border-secondary'})
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Styling field bawaan UserCreationForm
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control-clean'})