# Browser tests use Playwright for Python

Status: proposed (confirmed at Gate 1)
Ledger: D-014

The standard runs end-to-end tests with Playwright in TypeScript. This project has no Node toolchain, and adding one only for tests would double the dependency and CI surface. End-to-end tests use `pytest-playwright` with `axe-playwright-python` for the accessibility check, live in `e2e/test_*.py`, and carry the ledger id in the test name (`test_R017_reject_needs_reason`), which the ledger check already recognises.
