from decimal import Decimal
from typing import Any

from django import template

from core.formats import rupiah as format_rupiah

register = template.Library()


@register.filter
def rupiah(value: Decimal | int | float | str | None) -> str:
    """Format amount as Indonesian Rupiah (e.g. Rp 1.850.000)."""
    return format_rupiah(value)


@register.filter
def sub(value: Any, arg: Any) -> int:
    """Mengurangi value dengan arg."""
    try:
        return int(value) - int(arg)
    except ValueError, TypeError:
        return 0


@register.filter
def format_wa(phone: Any) -> str:
    """D-WA-01: Convert Indonesian phone numbers to wa.me format (08xxx -> 628xxx)."""
    digits = "".join(c for c in str(phone) if c.isdigit())
    if digits.startswith("0"):
        return "62" + digits[1:]
    return digits
