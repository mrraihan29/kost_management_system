from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/", views.admin_dashboard, name="dashboard"),
    path("settings/locations/", views.location_list, name="location_list"),
    path("settings/locations/<int:pk>/edit/", views.location_update, name="location_update"),
    # Room Management (B-CRUD-04)
    path("rooms/", views.room_list, name="room_list"),
    path("rooms/add/", views.room_create, name="room_add"),
    path("rooms/<int:pk>/edit/", views.room_update, name="room_edit"),
    path("rooms/<int:pk>/delete/", views.room_delete, name="room_delete"),
    path("styleguide/", views.styleguide, name="styleguide"),
]
