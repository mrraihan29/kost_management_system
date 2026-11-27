"""Tenant portal session helpers (R-007, D-016)."""

from django.http import HttpRequest

from tenants.models import TenantContract

SESSION_CONTRACT_KEY = "verified_contract_id"


def portal_contract(request: HttpRequest) -> TenantContract | None:
    """Return the active TenantContract for the current portal session, or clear it and return None."""
    contract_id = request.session.get(SESSION_CONTRACT_KEY)
    if not contract_id:
        return None
    contract = (
        TenantContract.objects.select_related("tenant", "room__kost_location")
        .filter(pk=contract_id, is_active=True)
        .first()
    )
    if contract is None:
        request.session.pop(SESSION_CONTRACT_KEY, None)
    return contract
