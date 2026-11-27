# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Check docs/ledger.yaml against rules LC01-LC10 (docs/SPEC.md sections 4-5)."""

import argparse
import re
import sys
from pathlib import Path
from typing import Literal, NamedTuple

import yaml

Gate = Literal["discover", "design"]
REQUIRE_CHOICES = frozenset({"tickets", "tests"})

ID_RE = re.compile(r"^[RD]-\d{3,}$")
LINK_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*-\d+)@(\d+)$")
ENTRY_KEYS = {
    "id",
    "type",
    "version",
    "status",
    "topic",
    "answer",
    "recommendation",
    "statement",
    "acceptance",
    "links",
    "prototype_question",
    "superseded_by",
}
LINK_KEYS = {"decisions", "tickets"}
STATUSES = {"active", "deferred", "superseded"}


class Problem(NamedTuple):
    rule: str
    where: str
    message: str


class LedgerError(Exception):
    """Ledger cannot be read or parsed (exit code 2)."""


def load(path: Path) -> dict:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        raise LedgerError(f"cannot read {path}: {e}") from e
    except yaml.YAMLError as e:
        raise LedgerError(f"invalid YAML in {path}: {e}") from e
    if not isinstance(data, dict):
        raise LedgerError(f"{path}: top level must be a mapping")
    return data


def _int(x, lo=None, hi=None) -> bool:
    return (
        isinstance(x, int)
        and not isinstance(x, bool)
        and (lo is None or lo <= x)
        and (hi is None or x <= hi)
    )


def _str(x) -> bool:
    return isinstance(x, str) and x.strip() != ""


def _links(e: dict, key: str) -> list[str]:
    """Well-formed link strings of an entry (malformed ones are LC02's job)."""
    links = e.get("links")
    vals = links.get(key) if isinstance(links, dict) else None
    return (
        [v for v in vals if isinstance(v, str) and LINK_RE.match(v)]
        if isinstance(vals, list)
        else []
    )


def _header(data: dict) -> list[Problem]:
    out = []

    def bad(msg):
        out.append(Problem("LC01", "header", msg))

    if not _int(data.get("schema_version")) or data["schema_version"] != 1:
        bad("schema_version must be 1")
    if not _str(data.get("project")):
        bad("project must be a non-empty string")
    g = data.get("test_globs", [])
    if not (isinstance(g, list) and all(isinstance(x, str) for x in g)):
        bad("test_globs must be a list of strings")
    na = data.get("na_topics", {})
    if not isinstance(na, dict):
        bad("na_topics must be a mapping of topic number to reason")
    else:
        for k, v in na.items():
            if not _int(k, 1, 14):
                bad(f"na_topics key {k!r} must be an int 1..14")
            elif not _str(v):
                bad(f"na_topics[{k}] needs a non-empty reason")
    if not isinstance(data.get("entries"), list) or not data["entries"]:
        bad("entries must be a non-empty list")
    return out


def _entry_schema(e: dict, where: str) -> list[Problem]:
    out = []

    def bad(msg):
        out.append(Problem("LC02", where, msg))

    for k in sorted(set(e) - ENTRY_KEYS, key=str):
        bad(f"unknown key {k!r}")
    id_ = e.get("id")
    if not (isinstance(id_, str) and ID_RE.match(id_)):
        bad("id must match ^[RD]-\\d{3,}$")
    elif e.get("type") != ("requirement" if id_[0] == "R" else "decision"):
        bad(f"type must be {'requirement' if id_[0] == 'R' else 'decision'} for id {id_}")
    if not _int(e.get("version"), 1):
        bad("version must be an int >= 1")
    if e.get("status") not in STATUSES:
        bad("status must be active, deferred or superseded")
    if not _int(e.get("topic"), 1, 14):
        bad("topic must be an int 1..14")
    for k in ("answer", "statement"):
        if not _str(e.get(k)):
            bad(f"{k} must be a non-empty string")
    acc = e.get("acceptance", [])
    if not (isinstance(acc, list) and all(isinstance(x, str) for x in acc)):
        bad("acceptance must be a list of strings")
    links = e.get("links", {})
    if not isinstance(links, dict):
        bad("links must be a mapping")
    else:
        for k, vals in links.items():
            if k not in LINK_KEYS:
                bad(f"unknown links key {k!r}")
            elif not isinstance(vals, list):
                bad(f"links.{k} must be a list")
            else:
                for v in vals:
                    if not (isinstance(v, str) and LINK_RE.match(v)):
                        bad(f"links.{k} item {v!r} must look like KEY-1@1")
    if e.get("status") == "deferred" and not _str(e.get("prototype_question")):
        bad("deferred entry needs prototype_question")
    if e.get("status") == "superseded" and not _str(e.get("superseded_by")):
        bad("superseded entry needs superseded_by")
    if e.get("answer") == "autonomous default" and not _str(e.get("recommendation")):
        bad("autonomous default needs recommendation")
    return out


def _tested(rid: str, data: dict, root: Path) -> bool:
    pat = re.compile(rf"(?<![A-Za-z0-9_-]){re.escape(rid)}(?!\d)")
    globs = data.get("test_globs")
    for g in globs if isinstance(globs, list) else []:
        if not isinstance(g, str):
            continue
        try:
            files = list(Path(root).glob(g))
        except NotImplementedError, ValueError:
            continue  # absolute or invalid glob: matches nothing
        for f in files:
            try:
                if f.is_file() and pat.search(f.read_text(encoding="utf-8", errors="replace")):
                    return True
            except OSError:
                continue
    return False


def check(
    data: dict,
    *,
    gate: Gate = "design",
    require: frozenset[str] = frozenset(),
    root: Path = Path("."),
) -> list[Problem]:
    out = _header(data)
    raw = data.get("entries")
    raw = raw if isinstance(raw, list) else []

    valid: list[dict] = []  # mappings with a usable id
    seen: set[str] = set()
    for i, e in enumerate(raw):
        if not isinstance(e, dict):
            out.append(Problem("LC02", f"entries[{i}]", "entry must be a mapping"))
            continue
        usable = isinstance(e.get("id"), str) and bool(ID_RE.match(e["id"]))
        out += _entry_schema(e, e["id"] if usable else f"entries[{i}]")
        if not usable:
            continue
        if e["id"] in seen:
            out.append(Problem("LC03", e["id"], "duplicate id"))
            continue  # first occurrence is the one other rules use
        seen.add(e["id"])
        valid.append(e)
    by_id = {e["id"]: e for e in valid}

    for e in valid:
        id_ = e["id"]
        is_req = id_[0] == "R"
        active = e.get("status") == "active"
        acc = e.get("acceptance")
        if is_req and active and not (isinstance(acc, list) and any(_str(a) for a in acc)):
            out.append(
                Problem("LC04", id_, "active requirement needs at least one acceptance item")
            )
        if gate == "design" and e.get("status") == "deferred":
            out.append(
                Problem(
                    "LC05",
                    id_,
                    f"deferred at gate design; resolve prototype_question: {e.get('prototype_question')}",
                )
            )
        sup = e.get("superseded_by")
        if _str(sup) and sup not in by_id:
            out.append(Problem("LC06", id_, f"superseded_by {sup} does not exist"))
        for link in _links(e, "decisions"):
            ref, n = LINK_RE.match(link).groups()
            t = by_id.get(ref)
            if t is None:
                out.append(
                    Problem("LC06", id_, f"links.decisions {link} target {ref} does not exist")
                )
            elif ref[0] != "D":
                out.append(
                    Problem("LC06", id_, f"links.decisions {link} target {ref} is not a decision")
                )
            elif t.get("status") == "superseded":
                out.append(
                    Problem("LC06", id_, f"links.decisions {link} target {ref} is superseded")
                )
            elif _int(t.get("version")) and t["version"] != int(n):
                out.append(
                    Problem(
                        "LC07",
                        id_,
                        f"links.decisions {link} is stale ({ref} is version {t['version']})",
                    )
                )
        for link in _links(e, "tickets"):
            n = LINK_RE.match(link).group(2)
            if _int(e.get("version")) and e["version"] != int(n):
                out.append(
                    Problem(
                        "LC07",
                        id_,
                        f"links.tickets {link} is stale ({id_} is version {e['version']})",
                    )
                )
        if is_req and active and "tickets" in require and not _links(e, "tickets"):
            out.append(Problem("LC09", id_, "active requirement has no links.tickets"))
        if is_req and active and "tests" in require and not _tested(id_, data, root):
            out.append(Problem("LC10", id_, "no test file under test_globs mentions this id"))

    na = data.get("na_topics")
    covered = {e["topic"] for e in valid if _int(e.get("topic"), 1, 14)}
    covered |= {
        k for k, v in (na.items() if isinstance(na, dict) else []) if _int(k, 1, 14) and _str(v)
    }
    for t in range(1, 15):
        if t not in covered:
            out.append(Problem("LC08", "header", f"topic {t} has no entry and no na_topics reason"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ledger_check", description="Check a decision ledger.")
    ap.add_argument("path", nargs="?", default="docs/ledger.yaml")
    ap.add_argument("--gate", choices=["discover", "design"], default="design")
    ap.add_argument("--require", default="", help="comma list from: tickets, tests")
    ap.add_argument("--root", default=".")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(errors="replace")
    req = frozenset(x.strip() for x in a.require.split(",") if x.strip())
    if req - REQUIRE_CHOICES:
        print(
            f"ledger_check: error: unknown --require value(s): {', '.join(sorted(req - REQUIRE_CHOICES))}",
            file=sys.stderr,
        )
        return 2
    try:
        data = load(Path(a.path))
    except LedgerError as e:
        print(f"ledger_check: error: {e}", file=sys.stderr)
        return 2
    ps = sorted(
        check(data, gate=a.gate, require=req, root=Path(a.root)), key=lambda p: (p.rule, p.where)
    )
    for p in ps:
        print(f"{p.rule} {p.where}: {p.message}")
    n = len(data["entries"]) if isinstance(data.get("entries"), list) else 0
    print(
        f"ledger_check: FAIL ({len(ps)} problems, gate={a.gate})"
        if ps
        else f"ledger_check: OK ({n} entries, gate={a.gate})"
    )
    return 1 if ps else 0


if __name__ == "__main__":
    raise SystemExit(main())
