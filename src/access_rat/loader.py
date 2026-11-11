"""Loading and validating the input CSV files.

Expected files and columns (header names are case-insensitive):

    users.csv              user, department, job_title
    memberships.csv        user, group
    group_permissions.csv  group, permission
    sod_rules.csv          permission_a, permission_b   (optional: rule_id, description)
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Iterable

from .errors import ValidationError
from .model import Dataset, SodRule

USERS_COLUMNS = ("user", "department", "job_title")
MEMBERSHIP_COLUMNS = ("user", "group")
GROUP_PERMISSION_COLUMNS = ("group", "permission")
SOD_REQUIRED = ("permission_a", "permission_b")
SOD_OPTIONAL = ("rule_id", "description")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_rows(
    path: Path,
    required: Iterable[str],
    optional: Iterable[str],
    problems: list[str],
) -> list[tuple[int, dict[str, str]]]:
    """Read a CSV into (line_number, row) pairs, recording problems rather than raising."""
    required = tuple(required)
    optional = tuple(optional)
    name = path.name
    if not path.is_file():
        problems.append(f"{name}: file not found at {path}")
        return []
    try:
        handle = path.open(newline="", encoding="utf-8-sig")
    except OSError as exc:  # pragma: no cover - depends on the filesystem
        problems.append(f"{name}: cannot be opened ({exc})")
        return []
    with handle:
        reader = csv.reader(handle)
        try:
            header_raw = next(reader)
        except StopIteration:
            problems.append(f"{name}: file is empty (expected a header row: {', '.join(required)})")
            return []
        header = [h.strip().lower() for h in header_raw]
        missing = [c for c in required if c not in header]
        if missing:
            problems.append(
                f"{name}: missing required column(s): {', '.join(missing)} "
                f"(found: {', '.join(h for h in header if h) or 'none'})"
            )
            return []
        index = {col: header.index(col) for col in (*required, *optional) if col in header}
        rows: list[tuple[int, dict[str, str]]] = []
        for line_no, raw in enumerate(reader, start=2):
            if not any(cell.strip() for cell in raw):
                continue  # ignore blank lines
            row: dict[str, str] = {}
            for col, idx in index.items():
                value = raw[idx].strip() if idx < len(raw) else ""
                row[col] = value
            blanks = [c for c in required if not row.get(c)]
            if blanks:
                problems.append(f"{name} line {line_no}: empty value for {', '.join(blanks)}")
                continue
            rows.append((line_no, row))
    return rows


def load_dataset(
    users_path: Path | str,
    memberships_path: Path | str,
    group_permissions_path: Path | str,
    sod_rules_path: Path | str | None = None,
) -> Dataset:
    """Load, validate and return a Dataset. Raises ValidationError listing every problem."""
    users_path = Path(users_path)
    memberships_path = Path(memberships_path)
    group_permissions_path = Path(group_permissions_path)
    sod_path = Path(sod_rules_path) if sod_rules_path else None

    problems: list[str] = []
    warnings: list[str] = []
    hashes: dict[str, str] = {}

    # users
    users: dict[str, tuple[str, str]] = {}
    for line_no, row in _read_rows(users_path, USERS_COLUMNS, (), problems):
        user = row["user"]
        if user in users:
            problems.append(f"{users_path.name} line {line_no}: duplicate user '{user}'")
            continue
        users[user] = (row["department"], row["job_title"])

    # memberships
    members: dict[str, set[str]] = {}
    seen_pairs: set[tuple[str, str]] = set()
    duplicate_memberships = 0
    for line_no, row in _read_rows(memberships_path, MEMBERSHIP_COLUMNS, (), problems):
        user, group = row["user"], row["group"]
        if users and user not in users:
            problems.append(
                f"{memberships_path.name} line {line_no}: user '{user}' is not listed in {users_path.name}"
            )
            continue
        if (user, group) in seen_pairs:
            duplicate_memberships += 1
            continue
        seen_pairs.add((user, group))
        members.setdefault(group, set()).add(user)
    if duplicate_memberships:
        warnings.append(f"{memberships_path.name}: {duplicate_memberships} duplicate membership row(s) ignored")

    # group permissions
    perms: dict[str, set[str]] = {}
    seen_gp: set[tuple[str, str]] = set()
    duplicate_gp = 0
    for _line_no, row in _read_rows(group_permissions_path, GROUP_PERMISSION_COLUMNS, (), problems):
        key = (row["group"], row["permission"])
        if key in seen_gp:
            duplicate_gp += 1
            continue
        seen_gp.add(key)
        perms.setdefault(row["group"], set()).add(row["permission"])
    if duplicate_gp:
        warnings.append(f"{group_permissions_path.name}: {duplicate_gp} duplicate row(s) ignored")

    # SoD rules (optional file)
    rules: list[SodRule] = []
    if sod_path is not None:
        seen_ids: set[str] = set()
        for line_no, row in _read_rows(sod_path, SOD_REQUIRED, SOD_OPTIONAL, problems):
            a, b = row["permission_a"], row["permission_b"]
            if a == b:
                problems.append(f"{sod_path.name} line {line_no}: permission_a and permission_b are identical ('{a}')")
                continue
            rule_id = row.get("rule_id") or f"SOD-{len(rules) + 1:03d}"
            if rule_id in seen_ids:
                problems.append(f"{sod_path.name} line {line_no}: duplicate rule_id '{rule_id}'")
                continue
            seen_ids.add(rule_id)
            rules.append(SodRule(rule_id, a, b, row.get("description", "")))

    def _has_problem(path: Path) -> bool:
        return any(p.startswith(path.name) for p in problems)

    if users_path.is_file() and not users and not _has_problem(users_path):
        problems.append(f"{users_path.name}: contains no users")
    if group_permissions_path.is_file() and not perms and not _has_problem(group_permissions_path):
        problems.append(f"{group_permissions_path.name}: contains no group permissions")

    if problems:
        raise ValidationError(problems)

    # Cross-checks that only make sense once the files parsed cleanly.
    known_perms = {p for ps in perms.values() for p in ps}
    for rule in rules:
        for p in (rule.perm_a, rule.perm_b):
            if p not in known_perms:
                warnings.append(f"{rule.rule_id}: permission '{p}' is not granted by any group")
    group_names = set(members) | set(perms)
    folded: dict[str, str] = {}
    for g in sorted(group_names):
        key = g.casefold()
        if key in folded and folded[key] != g:
            warnings.append(f"groups '{folded[key]}' and '{g}' differ only by letter case; treated as different groups")
        folded.setdefault(key, g)

    for path in (users_path, memberships_path, group_permissions_path, sod_path):
        if path is not None and path.is_file():
            hashes[path.name] = _sha256(path)

    return Dataset(
        users=dict(sorted(users.items())),
        group_members={g: frozenset(m) for g, m in sorted(members.items())},
        group_perms={g: frozenset(p) for g, p in sorted(perms.items())},
        sod_rules=sorted(rules, key=lambda r: r.rule_id),
        input_hashes=hashes,
        warnings=warnings,
    )


def load_from_directory(
    data_dir: Path | str,
    users: Path | str | None = None,
    memberships: Path | str | None = None,
    group_permissions: Path | str | None = None,
    sod_rules: Path | str | None = None,
) -> Dataset:
    """Load from a directory with the conventional file names, allowing per-file overrides."""
    d = Path(data_dir)
    sod = Path(sod_rules) if sod_rules else (d / "sod_rules.csv")
    sod_explicit = sod_rules is not None
    sod_arg: Path | None = sod if (sod_explicit or sod.is_file()) else None
    ds = load_dataset(
        users or d / "users.csv",
        memberships or d / "memberships.csv",
        group_permissions or d / "group_permissions.csv",
        sod_arg,
    )
    if sod_arg is None:
        ds.warnings.append("No sod_rules.csv supplied: segregation-of-duties checks were skipped")
    return ds
