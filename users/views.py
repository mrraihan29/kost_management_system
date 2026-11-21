from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import get_object_or_404, redirect, render

from .forms import StaffCreationForm, StaffUpdateForm
from .models import AdminProfile, User


# Decorator Keamanan: Hanya Superuser yang boleh masuk sini
def is_superuser(user):
    return user.is_authenticated and user.is_superuser

@user_passes_test(is_superuser, login_url='/staff/dashboard/')
def staff_list(request):
    """
    Daftar Semua Staff (Admin Kost)
    """
    # Ambil user yang is_staff=True tapi bukan superuser
    staff_users = User.objects.filter(is_staff=True, is_superuser=False).select_related('admin_profile')
    
    return render(request, 'users/staff_list.html', {'staffs': staff_users})

@user_passes_test(is_superuser, login_url='/staff/dashboard/')
def staff_create(request):
    """
    Tambah Admin Baru
    """
    if request.method == 'POST':
        form = StaffCreationForm(request.POST)
        if form.is_valid():
            # 1. Simpan User (Username & Password)
            user = form.save(commit=False)
            user.is_staff = True # Wajib: Tandai sebagai Staff agar bisa login dashboard
            user.save()
            
            # 2. Simpan Profil & Lokasi
            location = form.cleaned_data['assigned_location']
            AdminProfile.objects.create(user=user, assigned_location=location)
            
            messages.success(request, f"Admin baru '{user.username}' berhasil dibuat untuk lokasi {location.name}.")
            return redirect('staff_list')
    else:
        form = StaffCreationForm()
        
    return render(request, 'users/staff_form.html', {'form': form, 'title': 'Tambah Staff Baru'})

@user_passes_test(is_superuser, login_url='/staff/dashboard/')
def staff_update(request, pk):
    """
    Edit Data Admin Kost (B-CRUD-03)
    """
    staff_user = get_object_or_404(User, pk=pk, is_staff=True, is_superuser=False)
    
    if request.method == 'POST':
        form = StaffUpdateForm(request.POST, instance=staff_user)
        if form.is_valid():
            user = form.save()
            
            # Update lokasi di AdminProfile
            location = form.cleaned_data['assigned_location']
            profile, created = AdminProfile.objects.get_or_create(user=user)
            profile.assigned_location = location
            profile.save()
            
            messages.success(request, f"Data admin '{user.username}' berhasil diperbarui.")
            return redirect('staff_list')
    else:
        form = StaffUpdateForm(instance=staff_user)
    
    return render(request, 'users/staff_form.html', {'form': form, 'title': f'Edit Staff: {staff_user.username}'})