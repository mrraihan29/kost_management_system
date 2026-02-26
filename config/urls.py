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
from django.http import JsonResponse
from core.views import home


# D-CFG-06: Health check endpoint (K-06 fix: cek koneksi DB)
def health_check(request):
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({'status': 'ok', 'database': 'connected'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'database': str(e)}, status=503)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_check, name='health_check'),
    path('', home, name='home'),
    path('accounts/login/', auth_views.LoginView.as_view(
        template_name='auth/login.html',
        extra_context={'hide_sidebar': True} 
    ), name='login'),
    
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='/accounts/login/'), name='logout'),
    path('', include('finance.urls')),
    path('staff/', include('core.urls')),
    path('staff/tenants/', include('tenants.urls')), 
    path('management/', include('users.urls')), 
    path('accounts/password_change/', auth_views.PasswordChangeView.as_view(template_name='auth/password_change.html'), name='password_change'),
    path('accounts/password_change/done/', auth_views.PasswordChangeDoneView.as_view(template_name='auth/password_change_done.html'), name='password_change_done'),

]   

# D-CFG-07: Serve media files (produksi idealnya via nginx/S3)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
