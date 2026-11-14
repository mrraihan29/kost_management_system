---
version: 1
slug: "docs-design-mockups-staff-home-html"
primary_target: "docs/design/mockups/staff-home.html"
related_targets: ["docs/design/mockups/tenant-invoices.html"]
---

# Surface brief: Staff home and Tenant invoices (design mockups)

Scope: `docs/design/mockups/staff-home.html` and `docs/design/mockups/tenant-invoices.html`, the two key screens for the Gate 1 mockup checkpoint. Visitor mode: Operate. Mobile-first at 390px, with a desktop composition at 1280px and up.

Audience and job: Staff on a phone, on site, clearing today's work (verify a transfer proof, record a meter reading, chase a late invoice, answer a damage report). Tenant on a phone, paying rent by manual bank transfer and uploading the proof.

Content and constraints: Indonesian only, Rupiah and Indonesian dates, system font stack (ledger D-007), Tailwind CSS (D-009), five Staff navigation items (R-028), bank details on the Tenant invoice (R-021), every unpaid invoice oldest first (R-022), rejection reason visible (R-017), short privacy notice (R-032). Demonstration data is synthetic.

Memorable moment: the room number plate. A person should leave remembering that each room is a plate and its colour is its payment state.

Unresolved: the owner will redesign the logo after this direction; the mockups carry the name only.

## Direction contract

THESIS: Every room is an enamel house-number plate and the plate's colour is the room's invoice state. Refuses the admin dashboard of metric cards over a table.

OWN-WORLD: Enamel blue #17409C for the shell and the primary action; porcelain ground #F4F6F3; ink #16212E. Plates are square, bold tabular numerals, a thin inner rim, in four glazes: green #0F7A47 paid, amber #E9A100 awaiting verification, red #C8281E late, blue needing a meter reading, and an unglazed dashed outline for an empty room. Each glaze carries a drawn corner mark so state never rests on colour alone. Colour lives only on plates and the shell; text stays ink. Three text sizes; rank is carried by weight.

STORY: Staff see the one thing to do next, do it, and watch the street of plates turn green. A Tenant sees what is owed, where to transfer it, and whether the proof was accepted.

FIRST VIEWPORT: At 390px, a blue sign plate with the location name; one next-task block led by an 84px room plate with its action button; then the work queue, each row led by a 44px plate; then the street of all room plates. The primary action sits in the next-task block, in thumb reach.

FORM: Enamel house-number plates and Jakarta street-name signs, position 6 of 7 on the ordered list. seed:22d1a117e2f916c2

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
