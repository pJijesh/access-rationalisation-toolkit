"""Run the full analysis and assemble headline metrics and output tables."""

from __future__ import annotations

import csv
import json
import statistics
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .analysis import MIXED, Analysis, analyse
from .design import Design, design_roles
from .impact import UserImpact, compute_impact
from .model import Dataset, Params
from .sod import conflicting_rules

CORE_SHARE = 0.5  # a role is "core" to a department when at least this share of its staff hold it


@dataclass
class Result:
    dataset: Dataset
    params: Params
    analysis: Analysis
    design: Design
    impacts: list[UserImpact]
    summary: dict
    outliers: list[tuple[str, str, str, str]]  # user, user dept, role id, role dept
    dept_patterns: list[dict]


def _median(values: list[int]) -> float:
    return float(statistics.median(values)) if values else 0.0


def run(ds: Dataset, params: Params) -> Result:
    an = analyse(ds, params)
    design = design_roles(ds, an, params)
    impacts = compute_impact(ds, an, design, params)
    role_dept = {r.role_id: r.department for r in design.roles}

    # Department patterns and cross-department assignments.
    outliers = []
    for imp in impacts:
        for role_id in imp.new_roles:
            rd = role_dept[role_id]
            if rd != MIXED and rd != imp.department:
                outliers.append((imp.user, imp.department, role_id, rd))
    outliers.sort()
    dept_patterns = []
    for dept in sorted({i.department for i in impacts}):
        staff = [i for i in impacts if i.department == dept]
        counts: dict[str, int] = {}
        for i in staff:
            for r in i.new_roles:
                counts[r] = counts.get(r, 0) + 1
        core = sorted(r for r, n in counts.items() if n / len(staff) >= CORE_SHARE)
        dept_patterns.append(
            {
                "department": dept,
                "headcount": len(staff),
                "core_roles": core,
                "avg_roles": round(sum(len(i.new_roles) for i in staff) / len(staff), 2),
                "avg_groups": round(sum(len(i.old_groups) for i in staff) / len(staff), 2),
                "cross_department_assignments": sum(1 for o in outliers if o[1] == dept),
            }
        )

    summary = build_summary(ds, params, an, design, impacts, outliers)
    return Result(ds, params, an, design, impacts, summary, outliers, dept_patterns)


def build_summary(
    ds: Dataset,
    params: Params,
    an: Analysis,
    design: Design,
    impacts: list[UserImpact],
    outliers: list[tuple[str, str, str, str]],
) -> dict:
    old_counts = [len(i.old_groups) for i in impacts]
    new_counts = [len(i.new_roles) for i in impacts]
    groups_before = len(ds.groups)
    roles_after = len(design.roles)
    merged_groups = sum(len(r.groups) for r in design.roles if len(r.groups) > 1)
    merged_roles = sum(1 for r in design.roles if len(r.groups) > 1)
    users_with_sod_before = sum(1 for i in impacts if i.sod_before)
    users_with_sod_after = sum(1 for i in impacts if i.sod_after)
    sod_inst_before = sum(len(i.sod_before) for i in impacts)
    sod_inst_after = sum(len(i.sod_after) for i in impacts)
    new_sod_instances = sum(len(i.diff.new_conflicts) for i in impacts)
    gainers = [i for i in impacts if i.diff.gains_access]
    losers = [i for i in impacts if i.diff.lost]
    perms_total = len({p for ps in ds.group_perms.values() for p in ps})
    role_list = sorted(design.roles, key=lambda r: r.role_id)
    identical_role_pairs = sum(
        1 for i, r in enumerate(role_list) for o in role_list[i + 1 :] if r.permissions == o.permissions
    )
    toxic_roles = {r.role_id: [x.rule_id for x in conflicting_rules(r.permissions, ds.sod_rules)] for r in design.roles}
    toxic_roles = {k: v for k, v in toxic_roles.items() if v}
    return {
        "tool_version": __version__,
        "parameters": {
            "threshold": params.threshold,
            "max_groups": params.max_groups,
            "spread_min": params.spread_min,
            "dominance": params.dominance,
            "max_gain_share": params.max_gain_share,
        },
        "inputs": {
            "users": len(ds.users),
            "groups": groups_before,
            "permissions": perms_total,
            "memberships": sum(len(m) for m in ds.group_members.values()),
            "sod_rules": len(ds.sod_rules),
            "sha256": dict(sorted(ds.input_hashes.items())),
        },
        "before": {
            "groups": groups_before,
            "groups_with_no_members": len(an.empty_groups),
            "groups_with_no_permissions": len(an.no_permission_groups),
            "identical_permission_pairs": sum(1 for p in an.pairs if p.kind == "identical permissions"),
            "near_identical_permission_pairs": sum(1 for p in an.pairs if p.kind == "near-identical permissions"),
            "avg_groups_per_user": round(sum(old_counts) / len(old_counts), 2),
            "median_groups_per_user": _median(old_counts),
            "max_groups_per_user": max(old_counts),
            "users_over_group_limit": sum(1 for n in old_counts if n > params.max_groups),
            "redundant_memberships": len(an.redundant),
            "users_with_sod_conflict": users_with_sod_before,
            "sod_conflict_instances": sod_inst_before,
            "groups_containing_sod_pair": len(an.toxic_groups),
        },
        "after": {
            "roles": roles_after,
            "identical_permission_pairs": identical_role_pairs,
            "roles_formed_by_merging": merged_roles,
            "groups_absorbed_into_merged_roles": merged_groups,
            "groups_retired": len(design.retired),
            "avg_roles_per_user": round(sum(new_counts) / len(new_counts), 2),
            "median_roles_per_user": _median(new_counts),
            "max_roles_per_user": max(new_counts),
            "users_over_group_limit": sum(1 for n in new_counts if n > params.max_groups),
            "users_with_sod_conflict": users_with_sod_after,
            "sod_conflict_instances": sod_inst_after,
            "sod_conflicts_newly_introduced": new_sod_instances,
            "roles_containing_sod_pair": len(toxic_roles),
            "cross_department_assignments": len(outliers),
        },
        "impact": {
            "users_gaining_access": len(gainers),
            "users_gaining_access_high": sum(1 for i in gainers if i.diff.severity == "HIGH"),
            "users_losing_access": len(losers),
            "users_unchanged": sum(1 for i in impacts if not i.diff.gained and not i.diff.lost),
            "merges_blocked": len(design.blocked),
        },
        "reduction": {
            "groups_removed": groups_before - roles_after,
            "groups_removed_pct": round(100 * (groups_before - roles_after) / groups_before, 1) if groups_before else 0.0,
        },
    }


# ----------------------------------------------------------------------------
# Output files
# ----------------------------------------------------------------------------


def _semi(items) -> str:
    return "; ".join(items)


def _write_csv(path: Path, headers: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(headers)
        w.writerows(rows)


def mapping_rows(res: Result) -> tuple[list[str], list[list]]:
    ds, design = res.dataset, res.design
    roles = {r.role_id: r for r in design.roles}
    gained = {i.user: set(i.diff.gained) for i in res.impacts}
    gainers_by_group: dict[str, int] = {}
    for g in ds.groups:
        if g in design.group_to_role:
            rp = roles[design.group_to_role[g]].permissions
            gainers_by_group[g] = sum(1 for u in ds.members_of(g) if gained[u] & rp)
        else:
            gainers_by_group[g] = 0
    headers = [
        "old_group",
        "old_members",
        "old_permissions",
        "action",
        "new_role_id",
        "new_role_name",
        "role_permissions",
        "permissions_added_to_group",
        "members_gaining_via_role",
        "cluster_min_similarity",
    ]
    rows = []
    for g in ds.groups:
        if g in design.group_to_role:
            role = roles[design.group_to_role[g]]
            rows.append(
                [
                    g,
                    len(ds.members_of(g)),
                    len(ds.perms_of(g)),
                    role.action,
                    role.role_id,
                    role.name,
                    len(role.permissions),
                    len(role.permissions - ds.perms_of(g)),
                    gainers_by_group[g],
                    f"{role.min_similarity:.3f}",
                ]
            )
        else:
            rows.append([g, len(ds.members_of(g)), len(ds.perms_of(g)), design.retired[g], "", "", 0, 0, 0, ""])
    return headers, rows


def impact_rows(res: Result) -> tuple[list[str], list[list]]:
    headers = [
        "user",
        "department",
        "job_title",
        "old_groups",
        "new_roles",
        "old_group_count",
        "new_role_count",
        "old_permission_count",
        "new_permission_count",
        "gains_access",
        "gained_permissions",
        "gained_via_roles",
        "loses_access",
        "lost_permissions",
        "sod_conflicts_before",
        "sod_conflicts_after",
        "sod_conflicts_new",
        "severity",
        "review_required",
    ]
    rows = []
    for i in res.impacts:
        rows.append(
            [
                i.user,
                i.department,
                i.job_title,
                _semi(i.old_groups),
                _semi(i.new_roles),
                len(i.old_groups),
                len(i.new_roles),
                i.old_permission_count,
                i.new_permission_count,
                "YES" if i.diff.gains_access else "no",
                _semi(i.diff.gained),
                _semi(i.gained_via),
                "YES" if i.diff.lost else "no",
                _semi(i.diff.lost),
                _semi(i.sod_before),
                _semi(i.sod_after),
                _semi(i.diff.new_conflicts),
                i.diff.severity,
                "YES" if i.review_required else "no",
            ]
        )
    return headers, rows


def roles_rows(res: Result) -> tuple[list[str], list[list]]:
    rows = []
    for r in res.design.roles:
        for p in sorted(r.permissions):
            rows.append([r.role_id, r.name, p])
    return ["role_id", "role_name", "permission"], rows


def write_outputs(res: Result, out_dir: Path | str, report_md: str, report_html: str) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, (h, r) in (
        ("mapping.csv", mapping_rows(res)),
        ("impact.csv", impact_rows(res)),
        ("roles.csv", roles_rows(res)),
    ):
        _write_csv(out / name, h, r)
        paths.append(out / name)
    (out / "report.md").write_text(report_md, encoding="utf-8", newline="\n")
    (out / "report.html").write_text(report_html, encoding="utf-8", newline="\n")
    (out / "summary.json").write_text(json.dumps(res.summary, indent=2, sort_keys=False) + "\n", encoding="utf-8", newline="\n")
    paths += [out / "report.md", out / "report.html", out / "summary.json"]
    return paths
