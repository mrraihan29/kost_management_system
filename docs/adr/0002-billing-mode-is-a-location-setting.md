# Billing mode and electricity billing are location settings

Status: accepted
Ledger: D-013 (implements R-027)

The code chose Ancol's billing by finding the word "ancol" in the location name, so renaming a location silently changed how its tenants are billed. Each location now stores `billing_mode` (`per_room_cycle` or `simultaneous`) and `bills_electricity`, set by the Owner; one billing service reads them. The migration sets Ancol to `per_room_cycle` with electricity and the other two to `simultaneous` without.

Considered: a per-room setting. Rejected because the owner described billing as a property of the kost, and per-room settings would let one building mix rhythms by accident.
