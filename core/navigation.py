"""Role-based navigation and Plat Nomor shell context (R-028, D-004)."""

from dataclasses import dataclass
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest

from core.scoping import NoLocation, location_for


@dataclass(frozen=True, slots=True)
class NavItem:
    """One navigation destination in the Staff/Owner shell."""

    label: str
    short_label: str
    url_name: str
    icon: str
    active_names: frozenset[str]
    current: bool = False


_STAFF_SPECS: tuple[NavItem, ...] = (
    NavItem("Beranda", "Beranda", "dashboard", "i-home", frozenset({"dashboard"})),
    NavItem(
        "Tagihan",
        "Tagihan",
        "invoice_list",
        "i-invoice",
        frozenset({"invoice_list", "invoice_detail", "print_receipt", "invoice_generate_bulk"}),
    ),
    NavItem(
        "Penghuni & Kamar",
        "Penghuni",
        "tenant_list",
        "i-users",
        frozenset(
            {
                "tenant_list",
                "tenant_add",
                "tenant_edit",
                "tenant_checkout",
                "tenant_delete",
                "tenant_assign_room",
                "room_list",
                "room_add",
                "room_edit",
                "room_delete",
            }
        ),
    ),
    NavItem(
        "Pengeluaran",
        "Pengeluaran",
        "operation_list",
        "i-expense",
        frozenset({"operation_list", "operation_add", "operation_edit", "operation_delete"}),
    ),
    NavItem(
        "Kerusakan",
        "Kerusakan",
        "ticket_list",
        "i-wrench",
        frozenset({"ticket_list", "ticket_update"}),
    ),
)

_OWNER_EXTRA_SPECS: tuple[NavItem, ...] = (
    NavItem(
        "Laporan Keuangan",
        "Laporan",
        "finance_report",
        "i-chart",
        frozenset({"finance_report", "export_finance_excel"}),
    ),
    NavItem(
        "Lokasi",
        "Lokasi",
        "location_list",
        "i-location",
        frozenset({"location_list", "location_update"}),
    ),
    NavItem(
        "Staff",
        "Staff",
        "staff_list",
        "i-staff",
        frozenset({"staff_list", "staff_add", "staff_edit"}),
    ),
)


def nav_items_for(
    user: AbstractBaseUser | AnonymousUser, current_url_name: str | None
) -> list[NavItem]:
    """Return ordered navigation items for Staff (5) or Owner (8); empty otherwise."""
    if not user.is_authenticated:
        return []
    is_owner = getattr(user, "is_superuser", False)
    if not is_owner and not getattr(user, "is_staff", False):
        return []

    specs = _STAFF_SPECS + _OWNER_EXTRA_SPECS if is_owner else _STAFF_SPECS
    return [
        NavItem(
            label=item.label,
            short_label=item.short_label,
            url_name=item.url_name,
            icon=item.icon,
            active_names=item.active_names,
            current=current_url_name in item.active_names if current_url_name else False,
        )
        for item in specs
    ]


def shell_context(request: HttpRequest) -> dict[str, Any]:
    """Provide navigation items and sign-plate labels for templates/base.html."""
    user = getattr(request, "user", AnonymousUser())
    url_name = request.resolver_match.url_name if request.resolver_match else None
    nav_items = nav_items_for(user, url_name)

    location_name = "Evy Kost"
    role_label = ""
    if user.is_authenticated:
        try:
            loc = location_for(user)
        except NoLocation:
            role_label = user.get_username()
        else:
            if loc is None:
                role_label = f"{user.get_username()} · Pemilik"
            else:
                location_name = loc.name
                role_label = f"{user.get_username()} · Staff {loc.name}"

    return {
        "nav_items": nav_items,
        "shell_location_name": location_name,
        "shell_role_label": role_label,
    }
