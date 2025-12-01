from django.shortcuts import render, redirect
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from .models import User, AdminProfile
from .forms import StaffCreationForm

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