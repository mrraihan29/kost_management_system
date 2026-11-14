# Keep Django with server-rendered templates and PostgreSQL

Status: accepted
Ledger: D-002, D-006, D-008

The standard's default for full-stack web is TypeScript. We keep the existing Python stack because 185 passing tests and every financial rule (row locking, invoice state machine, billing cycles) already exist in Django; a rewrite would redo all of that with no gain for Owner, Staff or Tenant.

- Backend: Python (latest series supported by Django 6.1, which supports 3.12 to 3.15; pick the newest series for which Pillow and psycopg publish wheels), Django 6.1, PostgreSQL 15 or newer (Django 6.1 dropped 14).
- Frontend: Django templates, Tailwind CSS built by the standalone CLI (no Node), and small inline JavaScript only where a page needs it (copy button, file preview). No JavaScript framework.

Deviation from the standard: the frontend is not TypeScript. Reason: pages are server-rendered and the JavaScript is a few dozen lines; a TypeScript build chain would add a toolchain for almost no code.
