# Design System: Evy Kost Management (EKM)

Direction: **Plat Nomor** (ledger D-004 v2, mockups approved at D-012). Every room is an enamel house-number plate; the plate's glaze is the room's invoice state. Enamel blue carries the shell and the primary action; colour otherwise lives only on plates. Text stays ink. Built with Tailwind CSS (D-009); tokens below are the `@theme` block.

Reference screens: `docs/design/mockups/staff-home.html`, `docs/design/mockups/tenant-invoices.html`.

## Colors

Ratios are WCAG 2.2 contrast, measured.

| Token | Value | Use | Contrast |
|---|---|---|---|
| `enamel` | #17409C | Shell (sign plate, desktop rail), primary button, links, meter-needed plate | white text 9.33:1; on porcelain 8.59:1 |
| `enamel-deep` | #10307A | Hover and pressed of `enamel` | white text 12.17:1 |
| `porcelain` | #F4F6F3 | Page ground | |
| `white` | #FFFFFF | Raised surfaces: next task, invoice blocks | |
| `ink` | #16212E | All text, heading and body | on porcelain 14.97:1, on white 16.27:1 |
| `ink-soft` | #586472 | Secondary text, meta, labels | on porcelain 5.55:1, on white 6.03:1 |
| `rule` | #DDE2DD | Row dividers (decorative) | n/a, not informational |
| `outline` | #7C8794 | Unglazed plates (unpaid, empty), field borders | on porcelain 3.36:1, on white 3.65:1 |
| `paid` | #0F7A47 | Paid plate | white numeral 5.39:1 |
| `wait` | #E9A100 | Awaiting-verification plate; focus ring outer colour | numeral #231A00 7.84:1 |
| `late` | #C8281E | Late plate, late text | white numeral 5.56:1; as text on porcelain 5.11:1 |
| `late-wash` | #FBEAE8 | Rejection notice ground | heading #8E1C15 7.75:1, body #5C1A15 11.18:1 |

Focus ring: 3px `wait` outline plus a 7px `ink` halo, so it reads on porcelain, white and enamel alike. Text selection: `enamel` ground, white text.

## Typography

System font stack only (D-007): `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`. Numerals are tabular wherever amounts, dates or room numbers line up. Rank is carried by weight; three text sizes plus display.

| Token | Size / line height | Weight | Use |
|---|---|---|---|
| `display` | 30px / 1.15 | 800 | Location name on the sign plate |
| `title` | 20px / 1.3 (24px on desktop) | 700 | Next task, invoice amount, page lead |
| `body` | 16px / 1.5 | 400, 600 for names, 700 for section headings | Everything else |
| `small` | 14px / 1.45 | 400 | Meta, status line, legend |
| `micro` | 12px / 1.4 | 400 | Mobile navigation labels, privacy notice only |
| plate numerals | 15px (street), 18px (row), 38px to 46px (next task) | 800 | Room plates |

### Spacing scale

Tailwind's 4px scale. In use: 4, 8, 12, 16, 24, 32, 40. Page gutter 16px on phone, 40px on desktop. More space above a section heading (32px) than below it (8px).

### Radius

| Token | Value | Use |
|---|---|---|
| plate | 10px (scales with plate size) | Room plates |
| control | 12px | Buttons, inputs, upload targets |
| surface | 16px | Sign plate, next-task block, invoice blocks |

Shadow: one only, `0 1px 0 #DDE2DD, 0 8px 24px -12px rgba(22,33,46,.18)`, on raised white surfaces.

## Components

| Component | default | hover | focus | disabled | loading | error | empty |
|---|---|---|---|---|---|---|---|
| Plate | Glaze + rim + corner mark | n/a (not interactive alone) | n/a | n/a | n/a | n/a | Unglazed, dashed `outline` border |
| Plate link (street, rows) | Plate | Row gets white wash | Focus ring | n/a | n/a | n/a | n/a |
| Sign plate | Enamel with inner white rim | n/a | n/a | n/a | n/a | n/a | n/a |
| Primary button | `enamel`, white, 48px min height | `enamel-deep` | Focus ring | 40% opacity, `aria-disabled` | Label "Menyimpan…", spinner, disabled | n/a | n/a |
| Secondary button | White, 2px `enamel` inset | `porcelain` ground | Focus ring | As primary | As primary | n/a | n/a |
| Upload target | Label wrapping a hidden file input | As its button style | Focus ring on the label | As primary | File name + "Mengunggah…" | Message under it: size or type, with the rule | n/a |
| Work-queue row | Plate, name, status line, right value | White wash | Focus ring | n/a | n/a | n/a | "Tidak ada yang perlu dikerjakan. Semua kamar beres." |
| Invoice block | White surface, plate, amount, breakdown, action | n/a | n/a | n/a | n/a | Rejection notice in `late-wash` | "Tidak ada tagihan. Terima kasih sudah membayar tepat waktu." |
| Rejection notice | `late-wash`, heading + reason | n/a | n/a | n/a | n/a | n/a | n/a |
| Navigation | Bottom bar (phone) or enamel rail (desktop); current item filled | Text to ink (phone), `enamel-deep` ground (rail) | Focus ring | n/a | n/a | n/a | n/a |
| Text field | White, 2px `outline` border, 48px | Border `ink-soft` | Focus ring | `porcelain` ground | n/a | Border `late`, message under it naming the fix | Placeholder shows an example, never the label |
| Message (Django messages) | Success: `paid` text on white; info: ink | n/a | n/a | n/a | n/a | Error: `late-wash` like the rejection notice | n/a |

## Key screens and mockups

| Screen | Mockup path | Approval (D- id) |
|---|---|---|
| Staff home | `docs/design/mockups/staff-home.html` (390px and 1440px) | D-012 |
| Tenant invoices | `docs/design/mockups/tenant-invoices.html` (390px) | D-012 |

Other screens (invoice detail with verification, onboarding form, issue-invoices preview, Owner home, reports, PIN entry) are built in this system during Build and reviewed in Verify.

## Accessibility

- Target: WCAG 2.2 AA.
- Checked automatically by axe inside the e2e tests, tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa`; zero critical or serious violations.
- State is never colour alone: every glaze has a drawn corner mark and every plate link has an `aria-label` with the state in words.
- Manual checks automation cannot do: keyboard-only flow, focus not obscured by the fixed bottom bar, targets at least 24x24 CSS px (plates are at least 44px), reduced motion respected, screen-reader names for controls.

## Rules

- Colour lives on plates and the shell. Body text never takes a glaze colour, except `late` for a late status line.
- No metric-card rows, no eyebrow labels above headings, no gradient text, no glass, no emoji as icons. Icons are drawn SVG at one 2px stroke.
- Amounts: `Rp 1.850.000` (dot thousands, no decimals). Dates: `14 November 2026`, short `14 Nov`.
