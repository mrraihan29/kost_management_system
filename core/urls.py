from django.urls import path
from . import views


urlpatterns = [
    path('dashboard/', views.admin_dashboard, name='dashboard'),
        path('settings/locations/', views.location_list, name='location_list'),
    path('settings/locations/<int:pk>/edit/', views.location_update, name='location_update'),
]