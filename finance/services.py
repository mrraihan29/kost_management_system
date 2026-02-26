from django.utils import timezone

from .models import Invoice


def sync_overdue_invoice_statuses(reference_date=None):
    """Update invoice BELUM_LUNAS yang sudah lewat jatuh tempo menjadi TELAT_BAYAR."""
    if reference_date is None:
        reference_date = timezone.now().date()

    return Invoice.objects.filter(
        status='BELUM_LUNAS',
        due_date__lt=reference_date,
    ).update(status='TELAT_BAYAR')
