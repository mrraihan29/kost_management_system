from django import template

register = template.Library()

@register.filter
def sub(value, arg):
    """Mengurangi value dengan arg"""
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def format_wa(phone):
    """
    D-WA-01: Convert nomor telepon Indonesia ke format wa.me
    08xxx → 628xxx, +628xxx → 628xxx
    """
    phone = ''.join(c for c in str(phone) if c.isdigit())
    if phone.startswith('0'):
        phone = '62' + phone[1:]
    return phone
