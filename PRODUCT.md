# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Owner**: one person who owns three kost (boarding house) locations and wants to see occupancy and money actually received across all of them.
- **Staff**: two or three people, each assigned to one location. They issue invoices, check transfer proofs, read electricity meters and handle damage reports, mostly on a phone while on site.
- **Tenant**: a mix of working adults and students renting one room. They want to know what they owe, where to transfer, and whether their payment was accepted, on a phone, without calling anyone.

There is no fourth user type.

## Product Purpose

Evy Kost Management (EKM) runs rent collection for three kost locations of about 80 rooms each. It issues monthly invoices, takes a photo of the bank transfer as proof, lets Staff approve or reject it, and shows the Owner the result. Success: a first-time Staff member verifies a payment and records a meter reading on a phone in under 2 minutes per invoice, and a Tenant uploads a proof in under 3 minutes on the first attempt.

## Positioning

Each location keeps its own billing rhythm inside one system: Ancol bills every room on that room's own cycle date and bills electricity from meter readings; the two other locations bill every room at once when Staff triggers it and use prepaid PLN tokens. Tenants need no account, only location, room number and a 6-digit PIN.

## Operating Context

- Payment is a manual bank transfer; the Tenant uploads a screenshot or photo of it. No payment gateway.
- Reminders go out as WhatsApp messages that Staff open from a link.
- An invoice moves through Belum Lunas, Menunggu Verifikasi, Lunas, or Telat.
- Staff work is a daily queue: proofs awaiting verification, meter readings missing, late invoices, new damage reports.
- Production runs at https://ekm.web.id and holds real tenant data.

## Capabilities and Constraints

- Existing Django application, server-rendered templates, PostgreSQL. No JavaScript framework. Tailwind CSS replaces Bootstrap.
- Indonesian only, including dates and Rupiah amounts. Mobile-first.
- System font stack only; no web font is downloaded.
- The first release reworks existing features and adds none beyond bank details per location and TOTP for the Owner.
- Full decision record: `docs/ledger.yaml`.

## Brand Commitments

- Name: Evy Kost Management, short form EKM.
- The owner will redesign the logo to follow the new interface. Colour and identity are open; the current indigo and the current charcoal-and-gold logo are not binding.
- The result must not read as a stock admin template and must not feel rigid or bureaucratic. Minimalist, yet professional.

## Evidence on Hand

- Real flows, statuses and screens in the codebase; seed data via `manage.py seed_data`.
- No testimonials, photography or marketing copy exist. Do not invent customers, prices or claims.

## Product Principles

1. The next action comes first: every screen opens on what this person must do now.
2. Money is exact: one amount, one basis, one format, everywhere.
3. One hand, one phone: every critical task completes on a 375px screen.
4. Status is never ambiguous: a Tenant always knows whether a payment is waiting, accepted or rejected, and why.

## Accessibility & Inclusion

WCAG 2.2 AA, checked with axe. Staff and Tenants are not assumed to be technical.
