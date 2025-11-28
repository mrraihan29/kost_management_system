"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from core.views import home

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    # URL Login Custom (Mengarah ke template baru kita)
        path('accounts/login/', auth_views.LoginView.as_view(
        template_name='auth/login.html',
        extra_context={'hide_sidebar': True}  # <--- INI KUNCINYA
    ), name='login'),
    # URL Logout (Redirect ke login lagi setelah logout)
    
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='/accounts/login/'), name='logout'),
    path('', include('finance.urls')),
    path('staff/', include('core.urls')), # Dashboard ada di /staff/dashboard/
        # TAMBAHKAN INI:
    path('staff/tenants/', include('tenants.urls')), 
]

# Tambahkan baris ini untuk melayani file media saat development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
