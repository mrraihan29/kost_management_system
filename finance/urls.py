from django.urls import path
from . import views

urlpatterns = [
    path('bayar/', views.public_payment_step1, name='public_payment_step1'),
    path('bayar/upload/', views.public_payment_step2, name='public_payment_step2'),
]