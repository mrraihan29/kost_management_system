from django.urls import path

from . import views

urlpatterns = [
    path("", views.tenant_list, name="tenant_list"),
    path("add/", views.TenantCreateView.as_view(), name="tenant_add"),  # URL Tambah
    path("<int:pk>/edit/", views.TenantUpdateView.as_view(), name="tenant_edit"),
    path("<int:pk>/checkout/", views.tenant_checkout, name="tenant_checkout"),
    path("<int:pk>/delete/", views.tenant_delete, name="tenant_delete"),
    path("<int:pk>/assign/", views.TenantContractCreateView.as_view(), name="tenant_assign_room"),
]
