from django.contrib import admin
from django.http import HttpResponseForbidden

from .forms import audit_location_setting_changes
from .models import OWNER_ONLY_LOCATION_FIELDS, KostLocation, Room


class KostLocationAdmin(admin.ModelAdmin):
    # W11/BQ-9: lokasi dengan histori tidak boleh dihapus dari admin
    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        if not request.user.is_superuser:
            return OWNER_ONLY_LOCATION_FIELDS
        return ()

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if (
            not request.user.is_superuser
            and request.method == "POST"
            and any(field in request.POST for field in OWNER_ONLY_LOCATION_FIELDS)
        ):
            return HttpResponseForbidden(
                "Hanya Pemilik yang dapat mengubah pengaturan penagihan atau rekening."
            )
        return super().change_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        before: dict[str, object] = {}
        if change and obj.pk:
            current = KostLocation.objects.get(pk=obj.pk)
            before = {field: getattr(current, field) for field in OWNER_ONLY_LOCATION_FIELDS}
        super().save_model(request, obj, form, change)
        if change and before:
            audit_location_setting_changes(request, obj, before)


class RoomAdmin(admin.ModelAdmin):
    # W11b/BQ-9: kamar dengan histori kontrak tidak boleh dihapus dari admin
    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(KostLocation, KostLocationAdmin)
admin.site.register(Room, RoomAdmin)
