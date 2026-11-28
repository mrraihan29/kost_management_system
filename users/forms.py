from django import forms
from django.contrib.auth.forms import UserCreationForm

from core.models import KostLocation

from .models import AdminProfile, User


class StaffCreationForm(UserCreationForm):
    """
    Form untuk membuat Admin Kost Baru + Assign Lokasi
    """

    assigned_location = forms.ModelChoiceField(
        queryset=KostLocation.objects.all(),
        required=True,
        label="Tugaskan di Lokasi",
        widget=forms.Select(attrs={"class": "form-select shadow-none border-secondary"}),
    )

    class Meta(UserCreationForm.Meta):  # pyright: ignore[reportAttributeAccessIssue]  (django-types omits Meta)
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Styling field bawaan UserCreationForm
        for field in self.fields:
            self.fields[field].widget.attrs.update({"class": "form-control-clean"})

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = True  # Wajib: Tandai sebagai Staff agar bisa login dashboard
        if commit:
            user.save()
            AdminProfile.objects.create(
                user=user, assigned_location=self.cleaned_data["assigned_location"]
            )
        return user


class StaffUpdateForm(forms.ModelForm):
    """
    Form untuk Edit Admin Kost (B-CRUD-03)
    """

    assigned_location = forms.ModelChoiceField(
        queryset=KostLocation.objects.all(),
        required=True,
        label="Tugaskan di Lokasi",
        widget=forms.Select(attrs={"class": "form-select shadow-none border-secondary"}),
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "is_active")
        labels = {
            "first_name": "Nama Depan",
            "last_name": "Nama Belakang",
            "email": "Email",
            "is_active": "Status Aktif",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if field != "is_active":
                self.fields[field].widget.attrs.update({"class": "form-control-clean"})
            else:
                self.fields[field].widget.attrs.update({"class": "form-check-input"})

        # Pre-fill lokasi dari AdminProfile
        if self.instance and hasattr(self.instance, "admin_profile"):
            self.fields["assigned_location"].initial = self.instance.admin_profile.assigned_location

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            profile, _ = AdminProfile.objects.get_or_create(user=user)
            profile.assigned_location = self.cleaned_data["assigned_location"]
            profile.save()
        return user
