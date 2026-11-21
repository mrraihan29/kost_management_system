from django.contrib import admin, messages
from django.db import transaction

from .models import ElectricityReading, Invoice, OperationCost, Payment


class InvoiceAdmin(admin.ModelAdmin):
    # (Poin Mentor): Ini akan membuat admin panel jauh lebih mudah dibaca
    list_display = ("id", "contract", "status", "due_date", "total_amount")
    list_filter = ("status", "contract__room__kost_location")
    search_fields = ("contract__tenant__full_name", "contract__room__room_number")

    # W1b/BQ-5: histori finansial tidak boleh dihapus dari admin
    def has_delete_permission(self, request, obj=None):
        return False

    # W1b/BQ-5: status/derived key selalu read-only; invoice LUNAS sepenuhnya view-only;
    # MENUNGGU_VERIFIKASI mengunci nilai finansial (kebijakan imutabilitas W2/W3)
    def get_readonly_fields(self, request, obj=None):
        protected = ("status", "total_amount", "billing_period_year", "billing_period_month")
        if obj is not None and obj.status == "LUNAS":
            return tuple(field.name for field in self.model._meta.fields)
        if obj is not None and obj.status == "MENUNGGU_VERIFIKASI":
            return protected + (
                "contract",
                "billing_period_start",
                "due_date",
                "base_rent_amount",
                "electricity_bill_amount",
            )
        return protected

    # W2 follow-up: serialize admin invoice edits on the invoice row so a stale admin POST
    # cannot rewrite finalized/awaiting financial values (closes the unlock+save TOCTOU).
    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if change and obj.pk:
                locked = Invoice.objects.select_for_update().get(pk=obj.pk)
                if locked.status == "LUNAS":
                    messages.error(request, "Tagihan yang sudah LUNAS tidak dapat diubah.")
                    return
                if locked.status == "MENUNGGU_VERIFIKASI":
                    obj.status = locked.status
                    obj.contract = locked.contract
                    obj.billing_period_start = locked.billing_period_start
                    obj.due_date = locked.due_date
                    obj.base_rent_amount = locked.base_rent_amount
                    obj.electricity_bill_amount = locked.electricity_bill_amount
                    messages.error(
                        request,
                        "Nilai finansial tagihan yang menunggu verifikasi tidak diubah.",
                    )
            super().save_model(request, obj, form, change)


class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "invoice", "uploaded_at", "verified_by")
    list_filter = ("verified_by",)

    # W1b/BQ-5/BQ-8: Payment adalah bukti — read-only, tanpa add/delete
    readonly_fields = (
        "invoice",
        "payment_proof_file",
        "uploaded_at",
        "status",
        "verified_by",
        "verified_at",
        "rejection_note",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ElectricityReadingAdmin(admin.ModelAdmin):
    # W1b/BQ-5 + RC1: reading terkunci setelah LUNAS; FK invoice selalu read-only
    # agar tidak ada workflow admin yang bisa memindahkan reading ke invoice lain.
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        protected = ("invoice",)
        if obj is not None and obj.invoice.status in ("LUNAS", "MENUNGGU_VERIFIKASI"):
            return tuple(field.name for field in self.model._meta.fields)
        return protected


class OperationCostAdmin(admin.ModelAdmin):
    list_display = ("incurred_date", "kost_location", "category", "amount", "admin")
    list_filter = ("kost_location", "category")


admin.site.register(Invoice, InvoiceAdmin)
admin.site.register(ElectricityReading, ElectricityReadingAdmin)
admin.site.register(Payment, PaymentAdmin)
admin.site.register(OperationCost, OperationCostAdmin)
