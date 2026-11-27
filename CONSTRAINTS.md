# Constraints

Last reviewed: 2026-11-14 by Raihan · Stack: Python, Django 6.1, PostgreSQL 15+, Tailwind CSS (docs/adr/0001-stack.md)
Read before writing code. Never weaken this file to make a change pass.

## Floor (always enforced)

- No new suppressions (`# noqa`, `# type: ignore`) without a reason in the commit
- No unimplemented stubs or empty `except` blocks
- No skipped or deleted tests without a reason
- No secrets in source
- This file is never weakened to make a change pass

## Enforced with numbers

| Dimension | Rule | Checked by | Runs at |
|---|---|---|---|
| Format + lint | Zero errors | `uv run ruff check` and `uv run ruff format --check` | every edit |
| Types | Zero errors, strict on new and changed modules | `uv run pyright` | every edit |
| Unit/integration | All pass | `uv run pytest` | task end, CI |
| Concurrency | All pass on PostgreSQL | `uv run pytest tests_postgres_concurrency.py` with `DATABASE_URL` set | CI |
| E2E | Every critical R- has a test named with its id; all pass | `uv run pytest e2e` | CI, after each deploy (smoke) |
| Accessibility | WCAG 2.2 AA, zero critical or serious violations | axe in the e2e tests, tags `wcag2a,wcag2aa,wcag21a,wcag21aa,wcag22aa` | CI |
| Dependencies | No known vulnerabilities | `osv-scanner scan source -r .` | CI |
| Secrets | None in source or history | `gitleaks detect --redact` | every edit, CI |
| Static analysis | No high findings | `semgrep scan --config p/default --config p/django --error` | CI |
| Django | No issues, deploy checks clean | `uv run python manage.py check --deploy` | CI |
| Migrations | None missing | `uv run python manage.py makemigrations --check --dry-run` | CI |
| Ledger | Every active R- has a ticket and a test | `uv run scripts/ledger_check.py docs/ledger.yaml --gate design --require tickets,tests` | CI |

## Project numbers

| Budget | Value | Ledger id |
|---|---|---|
| Scale | 3 locations x 80 rooms, 12 months of invoices | R-005 |
| Page response | Staff home, invoice list, room list under 1000 ms at p95 at that scale | R-005 |
| Staff task time | Verify one proof and record one meter reading on a 375px phone in under 120 s | R-003 |
| Tenant task time | PIN entry to upload confirmation in under 180 s | R-003 |
| Availability | 99% per month | R-030 |
| Data loss | At most 24 h (daily backup), near zero for migrations (pre-migration backup) | R-030, R-020 |
| Unit/integration suite | Under 5 minutes locally (today 25 minutes) | R-019 |
| Upload size | 5 MB, JPG or PNG | R-021 |

## Measured, not yet enforced (ratchets)

| Metric | Today | Direction |
|---|---|---|
| Mutation score on the diff (mutmut) | not yet measured | must not fall |

## Exceptions

| ID | Rule | Path | Reason | Owner | Expires |
|---|---|---|---|---|---|
| X-1 | Pyright strict | legacy modules | Strict applies to new modules; legacy modules stay basic until their logic moves into a new module (D-023) | Raihan | when each legacy module's logic moves into a new module |

## Definition of Done (standing)

- Acceptance criteria met and verified at runtime, not only compiled or typechecked.
- New behaviour has tests that fail without the change; existing tests pass; no regressions.
- Docs and ADRs updated where the change affects them.
- A rollback path exists for risky changes (migrations are expand-contract).
- The owner has reviewed before merge or deploy.
