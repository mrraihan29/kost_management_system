from django.contrib import admin
from .models import Invoice, ElectricityReading, Payment, OperationCost

class InvoiceAdmin(admin.ModelAdmin):
    # (Poin Mentor): Ini akan membuat admin panel jauh lebih mudah dibaca
    list_display = ('id', 'contract', 'status', 'due_date', 'total_amount')
    list_filter = ('status', 'contract__room__kost_location')
    search_fields = ('contract__tenant__full_name', 'contract__room__room_number')

class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'invoice', 'uploaded_at', 'verified_by')
    list_filter = ('verified_by',)

class OperationCostAdmin(admin.ModelAdmin):
    list_display = ('incurred_date', 'kost_location', 'category', 'amount', 'admin')
    list_filter = ('kost_location', 'category')

admin.site.register(Invoice, InvoiceAdmin)
admin.site.register(ElectricityReading)
admin.site.register(Payment, PaymentAdmin)
admin.site.register(OperationCost, OperationCostAdmin)