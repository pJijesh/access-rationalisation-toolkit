"""Markdown and HTML reports built from a single section model."""

from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass, field

from . import __version__
from .pipeline import Result


@dataclass
class Table:
    headers: list[str]
    rows: list[list[str]]
    note: str = ""


@dataclass
class Section:
    title: str
    paragraphs: list[str] = field(default_factory=list)
    table: Table | None = None
    bars: list[tuple[str, int, int]] | None = None  # label, before, after
    anchor: str = ""


def _join(items, limit: int | None = None) -> str:
    items = list(items)
    if limit is not None and len(items) > limit:
        return ", ".join(items[:limit]) + f" (+{len(items) - limit} more)"
    return ", ".join(items)


def _limit_rows(rows: list[list[str]], top: int, label: str, csv_name: str) -> tuple[list[list[str]], str]:
    if len(rows) <= top:
        return rows, ""
    return rows[:top], f"Showing the first {top} of {len(rows)} {label}. The full list is in {csv_name}."


def build_sections(res: Result) -> list[Section]:
    ds, an, design, params, s = res.dataset, res.analysis, res.design, res.params, res.summary
    b, a, imp = s["before"], s["after"], s["impact"]
    top = params.top
    sections: list[Section] = []

    # 1. Before and after
    rows = [
        ["Groups (before) / roles (after)", str(b["groups"]), str(a["roles"])],
        ["Groups with no members", str(b["groups_with_no_members"]), "0"],
        ["Groups granting no permissions", str(b["groups_with_no_permissions"]), "0"],
        ["Pairs of groups with identical permissions", str(b["identical_permission_pairs"]), str(a["identical_permission_pairs"])],
        ["Average groups per user", f"{b['avg_groups_per_user']:.2f}", f"{a['avg_roles_per_user']:.2f}"],
        ["Median groups per user", f"{b['median_groups_per_user']:g}", f"{a['median_roles_per_user']:g}"],
        ["Most groups held by one user", str(b["max_groups_per_user"]), str(a["max_roles_per_user"])],
        [f"Users holding more than {params.max_groups} groups", str(b["users_over_group_limit"]), str(a["users_over_group_limit"])],
        ["Users with a segregation-of-duties conflict", str(b["users_with_sod_conflict"]), str(a["users_with_sod_conflict"])],
        ["Segregation-of-duties conflict instances", str(b["sod_conflict_instances"]), str(a["sod_conflict_instances"])],
        ["Groups or roles holding both sides of a rule", str(b["groups_containing_sod_pair"]), str(a["roles_containing_sod_pair"])],
        ["Users who would gain access", "n/a", str(imp["users_gaining_access"])],
        ["Users who would lose access", "n/a", str(imp["users_losing_access"])],
    ]
    sections.append(
        Section(
            "Before and after",
            [
                f"The proposal reduces {b['groups']} legacy groups to {a['roles']} roles "
                f"({s['reduction']['groups_removed_pct']}% fewer). "
                f"{imp['users_unchanged']} of {s['inputs']['users']} users keep exactly the access they have today.",
                "Segregation-of-duties conflicts are carried forward, not fixed: the tool never removes access on its own. "
                "Resolving them is a decision for the business owner of each role.",
            ],
            Table(["Measure", "Before", "After"], rows),
            anchor="summary",
        )
    )

    # 2. Gains (the review list)
    gain_rows_all = [
        [
            i.user,
            i.department,
            i.job_title,
            i.diff.severity,
            _join(i.diff.gained),
            _join(i.gained_via),
            _join(i.diff.new_conflicts) or "none",
        ]
        for i in sorted(res.impacts, key=lambda i: (0 if i.diff.severity == "HIGH" else 1, i.user))
        if i.diff.gains_access
    ]
    gain_rows, note = _limit_rows(gain_rows_all, top, "users who gain access", "impact.csv")
    if gain_rows_all:
        paras = [
            f"{imp['users_gaining_access']} user(s) would hold a permission they do not hold today "
            f"({imp['users_gaining_access_high']} rated HIGH). Each needs a documented decision before cut-over: "
            "accept, assign a narrower role, or keep the original group. HIGH means the gain creates a new "
            "segregation-of-duties conflict or includes a sensitive action.",
        ]
        if params.max_gain_share > 0:
            paras.append("Re-run with --max-gain-share 0 to see the model that avoids every gain by keeping the affected groups apart.")
        tbl = Table(
            ["User", "Department", "Job title", "Severity", "Permissions gained", "Via role", "New SoD conflict"],
            gain_rows,
            note,
        )
    else:
        paras = ["No user would gain a permission under this proposal. The check compares every user's effective permissions before and after."]
        tbl = None
    sections.append(Section("Users who would gain access (review required)", paras, tbl, anchor="gains"))

    # 3. Blocked merges
    if design.blocked:
        brows = [
            [_join(x.groups_a), _join(x.groups_b), f"{x.similarity:.2f}", x.reason]
            for x in design.blocked[:top]
        ]
        sections.append(
            Section(
                "Merges the tool refused",
                [f"{len(design.blocked)} candidate merge(s) met the similarity threshold but were refused by a safety rule (segregation of duties or the gain limit)."],
                Table(["Group(s)", "Would merge with", "Similarity", "Reason"], brows,
                      f"Showing {min(top, len(design.blocked))} of {len(design.blocked)}." if len(design.blocked) > top else ""),
                anchor="blocked",
            )
        )

    # 4. SoD
    sod_rows_all = [
        [c.user, ds.users[c.user][1], c.rule_id, f"{c.perm_a} + {c.perm_b}",
         _join(c.groups_a), _join(c.groups_b), "same group" if c.single_group else "combination"]
        for c in an.conflicts
    ]
    sod_rows, note = _limit_rows(sod_rows_all, top, "conflicts", "the analysis output")
    if not ds.sod_rules:
        sod_paras = ["No sod_rules.csv was supplied, so this check was skipped."]
    else:
        sod_paras = [
            f"{len(ds.sod_rules)} rule(s) checked. {b['users_with_sod_conflict']} user(s) hold both sides of at least one rule today "
            f"({b['sod_conflict_instances']} instances). After the proposal: {a['users_with_sod_conflict']} user(s), "
            f"{a['sod_conflict_instances']} instances, of which {a['sod_conflicts_newly_introduced']} are newly introduced.",
        ]
        if an.toxic_groups:
            sod_paras.append(
                "Groups that contain both sides of a rule by themselves: "
                + _join(f"{g} ({', '.join(r)})" for g, r in an.toxic_groups.items()) + "."
            )
    sections.append(
        Section(
            "Segregation-of-duties conflicts today",
            sod_paras,
            Table(["User", "Job title", "Rule", "Conflicting permissions", "Granted by (first)", "Granted by (second)", "Source"], sod_rows, note)
            if sod_rows else None,
            anchor="sod",
        )
    )

    # 5. Group inventory
    mapping_by_group = {}
    roles = {r.role_id: r for r in design.roles}
    for g in ds.groups:
        if g in design.group_to_role:
            r = roles[design.group_to_role[g]]
            mapping_by_group[g] = (r.action, r.role_id)
        else:
            mapping_by_group[g] = (design.retired[g], "")
    inv = []
    for g in ds.groups:
        st = an.group_stats[g]
        inv.append([
            g, str(st.members), str(st.permissions),
            st.dominant_dept if st.members else "n/a",
            _join(st.flags) or "",
            mapping_by_group[g][0], mapping_by_group[g][1],
        ])
    sections.append(
        Section(
            "Group inventory and proposed action",
            ["Every legacy group with its size, dominant department (the department supplying at least "
             f"{int(params.dominance * 100)}% of members, otherwise Mixed), findings and proposed action."],
            Table(["Group", "Members", "Permissions", "Dominant department", "Findings", "Proposed action", "New role"], inv),
            anchor="groups",
        )
    )

    # 6. Near duplicates
    pair_rows_all = [
        [p.group_a, p.group_b, f"{p.perm_jaccard:.2f}", f"{p.member_jaccard:.2f}", p.kind, p.note]
        for p in an.pairs
    ]
    pair_rows, note = _limit_rows(pair_rows_all, top, "pairs", "the analysis output")
    sections.append(
        Section(
            "Overlapping and near-duplicate groups",
            [f"Pairs where either the permission sets or the member sets reach a Jaccard similarity of {params.threshold:.2f}. "
             f"{b['identical_permission_pairs']} pair(s) grant identical permissions."],
            Table(["Group A", "Group B", "Permission Jaccard", "Member Jaccard", "Kind", "Note"], pair_rows, note) if pair_rows else None,
            anchor="pairs",
        )
    )

    # 7. Excess groups
    ex_rows_all = [
        [u, ds.users[u][0], ds.users[u][1], str(n), _join(sorted(ds.user_groups[u]))]
        for u, n in an.excess_users
    ]
    ex_rows, note = _limit_rows(ex_rows_all, top, "users", "impact.csv")
    hist_before = Counter(len(i.old_groups) for i in res.impacts)
    hist_after = Counter(len(i.new_roles) for i in res.impacts)
    top_n = max(max(hist_before), max(hist_after))
    bars = [(str(n), hist_before.get(n, 0), hist_after.get(n, 0)) for n in range(0, top_n + 1)]
    red_by_group = Counter(g for _u, g in an.redundant)
    sections.append(
        Section(
            "Group counts per user",
            [f"{b['users_over_group_limit']} user(s) hold more than {params.max_groups} groups today; {a['users_over_group_limit']} would after the proposal. "
             f"{b['redundant_memberships']} membership(s) are redundant, meaning the user keeps identical access without them."
             + (" Groups with the most redundant memberships: "
                + _join(f"{g} ({n})" for g, n in sorted(red_by_group.items(), key=lambda kv: (-kv[1], kv[0]))[:5]) + "."
                if red_by_group else "")],
            Table(["User", "Department", "Job title", "Groups", "Group names"], ex_rows, note) if ex_rows else None,
            bars=bars,
            anchor="excess",
        )
    )

    # 8. Permission spread
    sp_rows_all = [[p, str(n), str(u)] for p, n, u in an.perm_spread]
    sp_rows, note = _limit_rows(sp_rows_all, top, "permissions", "the analysis output")
    sections.append(
        Section(
            "Permissions granted through many groups",
            [f"Permissions granted by at least {params.spread_min} different groups. These are candidates for a shared baseline role "
             "or for a decision about which group is the authoritative source."],
            Table(["Permission", "Groups granting it", "Users holding it"], sp_rows, note) if sp_rows else None,
            anchor="spread",
        )
    )

    # 9. Roles
    role_rows = [
        [r.role_id, r.name, r.department, str(len(r.groups)), str(len(r.permissions)), str(len(r.members)),
         f"{r.min_similarity:.2f}", _join(r.groups)]
        for r in design.roles
    ]
    sections.append(
        Section(
            "Proposed role model",
            ["Each role grants the union of the permissions of its source groups. The minimum similarity column is the weakest "
             "pairwise permission Jaccard inside the role; below 1.00 it means some members receive permissions their old group did not grant."],
            Table(["Role", "Name", "Department", "Source groups", "Permissions", "Members", "Min similarity", "Replaces"], role_rows),
            anchor="roles",
        )
    )

    # 10. Department patterns
    dp_rows = [
        [d["department"], str(d["headcount"]), f"{d['avg_groups']:.2f}", f"{d['avg_roles']:.2f}",
         _join(d["core_roles"]) or "none", str(d["cross_department_assignments"])]
        for d in res.dept_patterns
    ]
    out_rows_all = [[u, d, r, rd] for u, d, r, rd in res.outliers]
    out_rows, note = _limit_rows(out_rows_all, top, "assignments", "the analysis output")
    sections.append(
        Section(
            "Department patterns",
            ["Core roles are held by at least half of a department. A cross-department assignment is a user who would hold a role whose "
             f"members are mostly from another department. There are {a['cross_department_assignments']}; each is worth a question to the line manager."],
            Table(["Department", "Headcount", "Avg groups today", "Avg roles after", "Core roles", "Cross-department assignments"], dp_rows),
            anchor="departments",
        )
    )
    if out_rows:
        sections.append(
            Section("Cross-department assignments", [], Table(["User", "User's department", "Role", "Role's department"], out_rows, note), anchor="outliers")
        )

    # 11. Inputs
    notes = list(ds.warnings) or ["No data quality warnings."]
    input_rows = [[name, h[:16] + "..."] for name, h in sorted(ds.input_hashes.items())]
    sections.append(
        Section(
            "Inputs, parameters and data notes",
            [f"access-rat {__version__}. Threshold {params.threshold:.2f}, group limit {params.max_groups}, "
             f"dominance {params.dominance:.2f}, gain limit {int(round(params.max_gain_share * 100))}% of a role's members. "
             "The same inputs and parameters always produce the same output, so the SHA-256 prefixes below identify the data analysed."]
            + [f"Note: {n}" for n in notes],
            Table(["Input file", "SHA-256 (first 16 characters)"], input_rows),
            anchor="inputs",
        )
    )
    return sections


# ----------------------------------------------------------------------------
# Markdown
# ----------------------------------------------------------------------------


def _md_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_markdown(res: Result) -> str:
    out = ["# Access rationalisation report", ""]
    out.append(
        "Generated by access-rat. All output is advisory and requires human review before any change is made to a live system."
    )
    out.append("")
    for sec in build_sections(res):
        out += [f"## {sec.title}", ""]
        for p in sec.paragraphs:
            out += [p, ""]
        if sec.bars:
            out += ["| Groups held | Users before | Users after |", "| --- | ---: | ---: |"]
            out += [f"| {l} | {x} | {y} |" for l, x, y in sec.bars]
            out.append("")
        if sec.table:
            out.append("| " + " | ".join(sec.table.headers) + " |")
            out.append("| " + " | ".join("---" for _ in sec.table.headers) + " |")
            for row in sec.table.rows:
                out.append("| " + " | ".join(_md_cell(c) for c in row) + " |")
            out.append("")
            if sec.table.note:
                out += [f"_{sec.table.note}_", ""]
    return "\n".join(out).rstrip() + "\n"


# ----------------------------------------------------------------------------
# HTML
# ----------------------------------------------------------------------------

_CSS = """
:root{--bg:#f5f6f8;--card:#fff;--ink:#1b2430;--muted:#5b6675;--line:#dde1e7;--accent:#0f5c6e;--accent-soft:#e3f1f4;
--high:#b42318;--high-soft:#fdeceb;--med:#a15c07;--med-soft:#fdf3e1;--ok:#1d6b45;--bar-a:#9aa6b5;--bar-b:#0f5c6e}
@media (prefers-color-scheme:dark){:root{--bg:#12161c;--card:#1a2029;--ink:#e6eaf0;--muted:#9aa6b5;--line:#2b3340;
--accent:#6cc4d6;--accent-soft:#16323a;--high:#ff8f84;--high-soft:#3a1c1a;--med:#f0b35a;--med-soft:#38290f;--ok:#6fd3a0;--bar-a:#5b6675;--bar-b:#6cc4d6}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{background:var(--card);border-bottom:1px solid var(--line)}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px}
header .wrap{padding-top:28px;padding-bottom:22px}
h1{margin:0 0 4px;font-size:26px;letter-spacing:-.01em}
.sub{color:var(--muted);margin:0;max-width:78ch}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin:22px 0 4px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px}
.kpi .label{color:var(--muted);font-size:12.5px;text-transform:uppercase;letter-spacing:.05em}
.kpi .value{font-size:28px;font-weight:650;margin-top:2px;font-variant-numeric:tabular-nums}
.kpi .value small{font-size:15px;color:var(--muted);font-weight:500}
.kpi .hint{color:var(--muted);font-size:13px}
nav{display:flex;flex-wrap:wrap;gap:6px 16px;margin:18px 0 0;font-size:13.5px}
nav a{color:var(--accent);text-decoration:none}
nav a:hover{text-decoration:underline}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:20px 22px;margin:18px 0}
h2{margin:0 0 10px;font-size:18px}
p{margin:0 0 10px;max-width:90ch}
.tablewrap{overflow-x:auto;margin-top:8px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--muted);font-size:12.5px;white-space:nowrap;background:var(--card)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tbody tr:hover{background:var(--accent-soft)}
.badge{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600}
.HIGH{background:var(--high-soft);color:var(--high)}
.MEDIUM{background:var(--med-soft);color:var(--med)}
.note{color:var(--muted);font-size:13px;margin-top:8px}
.bars{margin:10px 0 14px;display:grid;grid-template-columns:auto 1fr;gap:6px 12px;align-items:center;font-size:13px;max-width:640px}
.bars .lab{color:var(--muted);text-align:right;white-space:nowrap}
.bar{height:9px;border-radius:5px}
.bar.a{background:var(--bar-a)}.bar.b{background:var(--bar-b);margin-top:3px}
.bars .cell{display:flex;flex-direction:column}
.legend{color:var(--muted);font-size:13px;margin-bottom:4px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin:0 4px 0 12px;vertical-align:baseline}
footer{color:var(--muted);font-size:13px;padding:6px 0 36px}
@media print{body{background:#fff}section,.kpi{break-inside:avoid}}
"""

_NUM = re.compile(r"^[\d.,%+-]+$")


def _html_table(t: Table) -> str:
    parts = ['<div class="tablewrap"><table><thead><tr>']
    num_cols = [
        bool(t.rows) and all(_NUM.match(r[i]) or r[i] in ("n/a", "") for r in t.rows) for i in range(len(t.headers))
    ]
    for h, n in zip(t.headers, num_cols):
        parts.append(f'<th class="{"num" if n else ""}">{html.escape(h)}</th>')
    parts.append("</tr></thead><tbody>")
    for row in t.rows:
        parts.append("<tr>")
        for cell, n in zip(row, num_cols):
            if cell in ("HIGH", "MEDIUM"):
                inner = f'<span class="badge {cell}">{cell}</span>'
            else:
                inner = html.escape(cell)
            parts.append(f'<td class="{"num" if n else ""}">{inner}</td>')
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    if t.note:
        parts.append(f'<p class="note">{html.escape(t.note)}</p>')
    return "".join(parts)


def _html_bars(bars: list[tuple[str, int, int]]) -> str:
    peak = max(max(x, y) for _l, x, y in bars) or 1
    out = ['<div class="legend"><i style="background:var(--bar-a)"></i>Users today<i style="background:var(--bar-b)"></i>Users after proposal'
           ' (bars show number of users by groups held)</div><div class="bars">']
    for label, x, y in bars:
        out.append(f'<div class="lab">{html.escape(label)} group(s)</div><div class="cell">'
                   f'<div class="bar a" style="width:{100 * x / peak:.1f}%" title="{x} users today"></div>'
                   f'<div class="bar b" style="width:{100 * y / peak:.1f}%" title="{y} users after"></div>'
                   f'<span class="note" style="margin:0">{x} today, {y} after</span></div>')
    out.append("</div>")
    return "".join(out)


def render_html(res: Result) -> str:
    s = res.summary
    b, a, imp = s["before"], s["after"], s["impact"]
    kpis = [
        ("Groups to roles", f'{b["groups"]} <small>to</small> {a["roles"]}', f'{s["reduction"]["groups_removed_pct"]}% fewer'),
        ("Average groups per user", f'{b["avg_groups_per_user"]:.2f} <small>to</small> {a["avg_roles_per_user"]:.2f}',
         f'most held today: {b["max_groups_per_user"]}'),
        ("Users with an SoD conflict", f'{b["users_with_sod_conflict"]} <small>to</small> {a["users_with_sod_conflict"]}',
         f'{a["sod_conflicts_newly_introduced"]} newly introduced'),
        ("Users who gain access", f'{imp["users_gaining_access"]}', (f'{imp["users_gaining_access_high"]} rated HIGH, review before cut-over' if imp["users_gaining_access"] else "no access is added")),
        ("Users who lose access", f'{imp["users_losing_access"]}', "the proposal never removes a permission"),
    ]
    secs = build_sections(res)
    body = []
    for sec in secs:
        body.append(f'<section id="{sec.anchor}"><h2>{html.escape(sec.title)}</h2>')
        for p in sec.paragraphs:
            body.append(f"<p>{html.escape(p)}</p>")
        if sec.bars:
            body.append(_html_bars(sec.bars))
        if sec.table:
            body.append(_html_table(sec.table))
        body.append("</section>")
    nav = "".join(f'<a href="#{s_.anchor}">{html.escape(s_.title)}</a>' for s_ in secs)
    cards = "".join(
        f'<div class="kpi"><div class="label">{html.escape(l)}</div><div class="value">{v}</div><div class="hint">{html.escape(h)}</div></div>'
        for l, v, h in kpis
    )
    return (
        "<!doctype html>\n<html lang=\"en-GB\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>Access rationalisation report</title>"
        f"<style>{_CSS}</style></head><body>"
        "<header><div class=\"wrap\"><h1>Access rationalisation report</h1>"
        "<p class=\"sub\">Proposed consolidation of legacy access groups into a smaller role model, with the evidence a reviewer needs: "
        "segregation-of-duties conflicts, overlaps, and every user whose access would change. Advisory only; a person must review before anything is changed.</p>"
        f"<div class=\"kpis\">{cards}</div><nav>{nav}</nav></div></header>"
        f"<main class=\"wrap\">{''.join(body)}</main>"
        f"<footer class=\"wrap\">Generated by access-rat {__version__}. Synthetic or supplied data only; no network access was used.</footer>"
        "</body></html>\n"
    )
