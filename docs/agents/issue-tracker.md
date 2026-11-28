# Issue Tracker

Issues for this repository live in **Plane** (workspace `naobi`, https://projects.naobi.dev) via Plane MCP. Do not fall back to GitHub Issues or local markdown; if Plane MCP is unavailable, stop and tell the owner.

## Project

- Project: **EKM** ("Evy Kost Management"), id `c476135a-c865-4d70-b11b-0cfe0035b842`
- Build tickets: `EKM-11` to `EKM-37` (children of `EKM-6`)

## States

- Backlog: `4c0809c4-e1e9-413d-a641-40c8e93a554c`
- Todo: `678b994f-08b4-4ef0-968d-6a938c0ce289`
- In Progress: `07374f2c-61aa-4570-b0a2-1785a786a514`
- In Review: `d78f5deb-4ff2-428a-8f98-386d0cccdace`
- Blocked: `cd6593ec-7fdd-4964-9d51-a866503bb1c5`
- Done: `93c6050b-30d0-47d3-903b-26f369e4efde`
- Cancelled: `7a5bb92d-2f52-4447-bd3f-47ac279427d1`

## Reading and updating tickets

- **Read tickets**: use `list_work_items` with `fields="sequence_id,name,description_html"` (do not use the retrieve-work-item tool; it fails with a validation error).
- **Blocking edges**: do not call `list work item relations` (validation error); check the project plan's dependency table.
- **Per ticket**: read acceptance criteria, file ownership and test plan first → set `In Progress` → implement and verify (including `gitleaks detect --redact` and ledger check) → commit with `(EKM-XX)` → comment verification evidence → set `Done` only when every acceptance criterion is met.
