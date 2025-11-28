from django import template

register = template.Library()

@register.filter
def sub(value, arg):
    """Mengurangi value dengan arg"""
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return 0
