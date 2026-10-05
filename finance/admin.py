from django.contrib import admin
from .models import Invoice, ElectricityReading, Payment, OperationCost


class InvoiceAdmin(admin.ModelAdmin):
    # (Poin Mentor): Ini akan membuat admin panel jauh lebih mudah dibaca
    list_display = ('id', 'contract', 'status', 'due_date', 'total_amount')
    list_filter = ('status', 'contract__room__kost_location')
    search_fields = ('contract__tenant__full_name', 'contract__room__room_number')

    # W1b/BQ-5: histori finansial tidak boleh dihapus dari admin
    def has_delete_permission(self, request, obj=None):
        return False

    # W1b/BQ-5: status/derived key selalu read-only; invoice LUNAS sepenuhnya view-only
    def get_readonly_fields(self, request, obj=None):
        protected = ('status', 'total_amount', 'billing_period_year', 'billing_period_month')
        if obj is not None and obj.status == 'LUNAS':
            return tuple(field.name for field in self.model._meta.fields)
        return protected


class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'invoice', 'uploaded_at', 'verified_by')
    list_filter = ('verified_by',)

    # W1b/BQ-5/BQ-8: Payment adalah bukti — read-only, tanpa add/delete
    readonly_fields = (
        'invoice', 'payment_proof_file', 'uploaded_at', 'status',
        'verified_by', 'verified_at', 'rejection_note',
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
        protected = ('invoice',)
        if obj is not None and obj.invoice.status == 'LUNAS':
            return tuple(field.name for field in self.model._meta.fields)
        return protected


class OperationCostAdmin(admin.ModelAdmin):
    list_display = ('incurred_date', 'kost_location', 'category', 'amount', 'admin')
    list_filter = ('kost_location', 'category')


admin.site.register(Invoice, InvoiceAdmin)
admin.site.register(ElectricityReading, ElectricityReadingAdmin)
admin.site.register(Payment, PaymentAdmin)
admin.site.register(OperationCost, OperationCostAdmin)
