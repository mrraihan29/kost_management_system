"""Indonesian display formatting helpers for Rupiah amounts and month names (EKM-18, R-009)."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MONTH_NAMES: tuple[str, ...] = (
    "Januari",
    "Februari",
    "Maret",
    "April",
    "Mei",
    "Juni",
    "Juli",
    "Agustus",
    "September",
    "Oktober",
    "November",
    "Desember",
)

_MINUS = "\u2212"


def month_name(month: int) -> str:
    """Return the Indonesian full month name for 1..12."""
    if not 1 <= month <= 12:
        raise ValueError(f"Month must be 1..12, got {month}")
    return MONTH_NAMES[month - 1]


def rupiah(value: Decimal | int | float | str | None) -> str:
    """Format an amount as whole Indonesian Rupiah (e.g. 'Rp 1.850.000', '−Rp 50.000')."""
    if value is None or value == "":
        return "Rp 0"
    try:
        dec = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation, ValueError:
        return "Rp 0"
    whole = int(dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    grouped = f"{abs(whole):,}".replace(",", ".")
    if whole < 0:
        return f"{_MINUS}Rp {grouped}"
    return f"Rp {grouped}"
