from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AdminProfile, User

# Daftarkan User dengan tampilan bawaan UserAdmin
admin.site.register(User, UserAdmin)
admin.site.register(AdminProfile)
