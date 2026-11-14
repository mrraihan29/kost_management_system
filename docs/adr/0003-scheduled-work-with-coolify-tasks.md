# Scheduled work runs as management commands triggered by Coolify

Status: accepted
Ledger: D-010

Three jobs run daily at 00:05 Asia/Jakarta: issue `per_room_cycle` invoices due in 7 days, mark unpaid invoices past their due date as late, and apply the retention rules. Each is an idempotent Django management command started by a Coolify scheduled task in the application container.

Considered: Celery with Redis. Rejected: three daily jobs do not justify a broker, a worker and a second process to monitor. Consequence: a missed run is caught up by the next one, because every command works from "everything due up to today", not "exactly today".
