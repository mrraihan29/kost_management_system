# Keep Django with server-rendered templates and PostgreSQL

Status: accepted
Ledger: D-002, D-006, D-008

The standard's default for full-stack web is TypeScript. We keep the existing Python stack because 185 passing tests and every financial rule (row locking, invoice state machine, billing cycles) already exist in Django; a rewrite would redo all of that with no gain for Owner, Staff or Tenant.

- Backend: Python 3.14 (chosen in EKM-13: officially supported across the full Django 5.2 → 6.0 → 6.1 upgrade path with published Pillow and psycopg binary wheels on Linux and Windows, and supported by the pinned uv toolchain), Django 6.1, PostgreSQL 15 or newer (Django 6.1 dropped 14; production verified at 17.7 in EKM-11).
- Frontend: Django templates, Tailwind CSS built by the standalone CLI (no Node), and small inline JavaScript only where a page needs it (copy button, file preview). No JavaScript framework.

Deviation from the standard: the frontend is not TypeScript. Reason: pages are server-rendered and the JavaScript is a few dozen lines; a TypeScript build chain would add a toolchain for almost no code.
