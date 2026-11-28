# Glossary

One word per concept. Code, docs and tickets use the English term; the UI uses the Indonesian label.

| Term | UI label | Meaning |
|---|---|---|
| Owner | Pemilik | The single superuser who sees every location. Not "admin" or "superadmin". |
| Staff | Staff | A user assigned to exactly one location. Not "admin kost". |
| Tenant | Penghuni | A person renting one room. Has no account; signs in with a PIN. |
| Location | Lokasi | One kost building (`KostLocation`). Three exist. |
| Room | Kamar | One rentable room at a location, identified by its room number. |
| Contract | Kontrak | One Tenant renting one Room from a start date. At most one active contract per room and per tenant. |
| PIN | PIN | The 6-digit code of an active contract, used with location and room number to open the Tenant portal. |
| Billing mode | Mode tagihan | A location setting: `per_room_cycle` (Ancol) or `simultaneous` (the other two). |
| Cycle date | Tanggal siklus | For a `per_room_cycle` contract: the contract start day of the month. Clamped to the month's last day. |
| Invoice | Tagihan | What a contract owes for one billing period. Not "bill" or "tagihan bulanan". |
| Issue | Terbitkan | Create invoices. Automatic for `per_room_cycle`, one Staff action for `simultaneous`. Not "generate". |
| Meter reading | Angka meteran | Start and end kWh for one invoice at a location that bills electricity. |
| Token room | Kamar token | A room on prepaid PLN tokens; no meter reading, no electricity on the invoice. |
| Proof | Bukti transfer | The image a Tenant uploads to show a bank transfer for one invoice (`Payment`). |
| Verification | Verifikasi | Staff approving or rejecting a proof. Rejection needs a reason the Tenant sees. |
| Invoice status | Status | `BELUM_LUNAS` (Belum dibayar), `MENUNGGU_VERIFIKASI` (Menunggu), `LUNAS` (Lunas), `TELAT_BAYAR` (Telat). |
| Late | Telat | An unpaid invoice past its due date. No fee is added. |
| Work queue | Perlu dikerjakan | The Staff list of proofs to verify, meter readings missing, late invoices and new damage reports. |
| Damage report | Laporan kerusakan | A Tenant's report of a problem in the room (`MaintenanceTicket`). |
| Operating cost | Pengeluaran | Money a location spends (`OperationCost`). |
| Income | Pemasukan | The total of invoices whose payment was verified in the period, dated by verification. |
| Plate | Plat | The UI element showing a room number in the colour of its invoice status. |
