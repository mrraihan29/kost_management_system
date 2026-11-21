from django.contrib import admin

from .models import KostLocation, Room


class KostLocationAdmin(admin.ModelAdmin):
    # W11/BQ-9: lokasi dengan histori tidak boleh dihapus dari admin
    def has_delete_permission(self, request, obj=None):
        return False


class RoomAdmin(admin.ModelAdmin):
    # W11b/BQ-9: kamar dengan histori kontrak tidak boleh dihapus dari admin
    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(KostLocation, KostLocationAdmin)
admin.site.register(Room, RoomAdmin)
