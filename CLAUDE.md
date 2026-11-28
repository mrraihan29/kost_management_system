# Evy Kost Management (EKM)

Rent collection for three kost locations (Owner, Staff, Tenants), live at https://ekm.web.id. Stack: Django 6.1, PostgreSQL 15+, Tailwind CSS, no JS framework (`docs/adr/0001-stack.md`).

## Commands
- Install: `uv sync`
- CSS build: `powershell -ExecutionPolicy Bypass -File scripts/tailwind.ps1` (Linux/CI: `sh scripts/tailwind.sh`)
- Format + lint: `uv run ruff check` and `uv run ruff format --check`
- Types: `uv run pyright`
- Unit tests (one file): `uv run pytest <path>`; all: `uv run pytest`
- E2E: `uv run pytest e2e` (added in EKM-36)
- UI audit (local Edge + axe): `node scripts/audit_ui.mjs <url> [out_dir]`
- Ledger check: `uv run scripts/ledger_check.py docs/ledger.yaml --gate design`
- Django checks: `uv run python manage.py check`; full suite takes about 20 seconds
- Windows PowerShell 5.1: use `; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }` (not `&&`), and pipe inline Python via `@' ... '@ | uv run python -`

## Boundaries
- Always: run the commands above on changed files before finishing; name each e2e test with its `R-xxx`; use the words in `GLOSSARY.md`; build UI with the `frontend-design` and `impeccable` skills to `DESIGN.md`.
- Ask first: schema changes, new dependencies, CI or deploy config, loosening any rule.
- Never: commit secrets, suppress a check without a written reason, skip or delete a test, weaken `CONSTRAINTS.md`, push or deploy without the owner's go. Production holds real tenant data: migrations are expand-contract.

## Read before coding
- `CONSTRAINTS.md`: quality bar and Definition of Done
- `GLOSSARY.md`: domain language
- `DESIGN.md`: Plat Nomor design system
- `docs/design/REPORT.md`: design, flows, security, test strategy
- `docs/ledger.yaml`: requirements (R-) and decisions (D-)
- Plane project EKM: roadmap EKM-1 to EKM-10, build tickets from Plan

## Agent skills

### Issue tracker
Plane project EKM via MCP. See `docs/agents/issue-tracker.md`.

### Domain docs
Single-context (`GLOSSARY.md` and `docs/adr/`). See `docs/agents/domain.md`.
