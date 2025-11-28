from django.urls import path
from . import views

urlpatterns = [
    path('bayar/', views.public_payment_step1, name='public_payment_step1'),
    path('bayar/upload/', views.public_payment_step2, name='public_payment_step2'),
    path('bayar/riwayat/', views.public_payment_history, name='public_payment_history'),
    path('verify/<int:payment_id>/<str:action>/', views.verify_payment, name='verify_payment'),
    path('invoice/', views.invoice_list, name='invoice_list'),
    path('invoice/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('operation/', views.operation_list, name='operation_list'),
    path('operation/add/', views.operation_create, name='operation_add'),
    path('invoice/<int:pk>/print/', views.print_receipt, name='print_receipt'),
    # URL LAPOR
    path('lapor/', views.public_report_create, name='public_report_create'),
    path('lapor/riwayat/', views.public_report_list, name='public_report_list'),
    # URL LAPOR (ADMIN SIDE):
    path('tickets/', views.admin_ticket_list, name='ticket_list'),
    path('tickets/<int:pk>/update/', views.admin_ticket_update, name='ticket_update'),
]