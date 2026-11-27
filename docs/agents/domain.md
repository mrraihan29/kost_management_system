# Domain Docs

Single-context repository. How engineering skills consume domain documentation when exploring or changing code.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root.
- **`docs/adr/`**: read ADRs relevant to the area you are touching.

## Use the glossary's vocabulary

Use the exact English terms defined in `GLOSSARY.md` for code, docs, commits, test names and Plane entries, and the Indonesian labels for UI text. Do not drift to avoided synonyms (e.g. use Owner/Staff/Tenant/Issue, not superadmin/admin kost/generate). If a concept is missing or unclear, raise it via `/domain-modeling`.

## Flag ADR conflicts

If a proposed change contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-000X (<topic>), worth reopening because…_
