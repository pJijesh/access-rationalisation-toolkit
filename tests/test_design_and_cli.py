
import pytest

from access_rat.analysis import analyse
from access_rat.cli import main
from access_rat.design import department_codes
from access_rat.loader import load_from_directory
from access_rat.model import Params
from access_rat.pipeline import run
from access_rat.report import render_html, render_markdown

from conftest import make_dataset


def test_identical_groups_merge_and_empty_groups_retire():
    users = {u: ("Ops", "Clerk") for u in ("u1", "u2", "u3")}
    ds = make_dataset(
        users,
        {"A": ["u1"], "B": ["u2"], "C": ["u3"]},
        {"A": ["x.view", "x.edit"], "B": ["x.edit", "x.view"], "C": ["y.view"], "ORPHAN": ["x.view"]},
    )
    d = run(ds, Params()).design
    assert d.group_to_role["A"] == d.group_to_role["B"] != d.group_to_role["C"]
    assert d.retired == {"ORPHAN": "retire (no members)"}
    assert len(d.roles) == 2


def test_complete_linkage_stops_chaining():
    # A~B and B~C pass 0.8 but A~C does not: all three must not end up together.
    base = [f"p{i}" for i in range(9)]
    users = {u: ("Ops", "Clerk") for u in ("u1", "u2", "u3")}
    ds = make_dataset(
        users,
        {"A": ["u1"], "B": ["u2"], "C": ["u3"]},
        {"A": base[:8], "B": base[:8] + ["z1"], "C": base[:7] + ["z1", "z2"]},
    )
    d = run(ds, Params(threshold=0.8, max_gain_share=1.0)).design
    assert len({d.group_to_role[g] for g in "ABC"}) >= 2


def test_non_identical_groups_in_different_departments_do_not_merge():
    users = {"u1": ("Finance", "Clerk"), "u2": ("Sales", "Rep")}
    perms = [f"p{i}" for i in range(9)]
    ds = make_dataset(users, {"F": ["u1"], "S": ["u2"]}, {"F": perms, "S": perms[:8] + ["other"]})
    d = run(ds, Params(threshold=0.7, max_gain_share=1.0)).design
    assert d.group_to_role["F"] != d.group_to_role["S"]


def test_identical_groups_in_different_departments_do_merge():
    users = {"u1": ("Finance", "Clerk"), "u2": ("Sales", "Rep")}
    ds = make_dataset(users, {"F": ["u1"], "S": ["u2"]}, {"F": ["a.view"], "S": ["a.view"]})
    d = run(ds, Params()).design
    assert d.group_to_role["F"] == d.group_to_role["S"]


def test_every_group_is_mapped_or_retired_and_roles_are_unions(demo_dir):
    ds = load_from_directory(demo_dir)
    res = run(ds, Params(threshold=0.7, max_gain_share=1.0))
    d = res.design
    assert set(d.group_to_role) | set(d.retired) == set(ds.groups)
    assert not set(d.group_to_role) & set(d.retired)
    for role in d.roles:
        assert role.permissions == frozenset().union(*(ds.perms_of(g) for g in role.groups))
    assert len({r.role_id for r in d.roles}) == len(d.roles)


def test_department_codes_are_unique():
    codes = department_codes(["Operations", "Operational Risk", "Finance"])
    assert len(set(codes.values())) == len(codes)


def test_demo_dataset_has_the_promised_shape(demo_dir):
    ds = load_from_directory(demo_dir)
    an = analyse(ds, Params())
    assert 145 <= len(ds.users) <= 155
    assert len(ds.groups) >= 36
    assert an.empty_groups and an.no_permission_groups
    assert an.conflicts, "demo data should contain deliberate SoD conflicts"
    assert any(p.kind == "identical permissions" for p in an.pairs)


def test_cli_end_to_end_and_fail_on_gain(tmp_path, capsys):
    data, out = tmp_path / "d", tmp_path / "o"
    assert main(["generate-demo", "--out", str(data)]) == 0
    assert main(["analyse", "--data", str(data), "--out", str(out), "--fail-on-gain"]) == 0
    for name in ("mapping.csv", "impact.csv", "roles.csv", "report.md", "report.html", "summary.json"):
        assert (out / name).is_file()
    assert main(["analyse", "--data", str(data), "--out", str(out), "--max-gain-share", "1", "--fail-on-gain"]) == 3


def test_reports_render_and_escape(demo_dir):
    res = run(load_from_directory(demo_dir), Params())
    md, html = render_markdown(res), render_html(res)
    assert md.startswith("# Access rationalisation report")
    assert "<script" not in html and html.startswith("<!doctype html>")
    assert "—" not in md and "—" not in html  # house style: no em-dashes


def test_html_escapes_hostile_names():
    users = {"u1": ("Ops", "<b>x</b>")}
    ds = make_dataset(users, {"G<script>": ["u1"]}, {"G<script>": ["a.view"]})
    html = render_html(run(ds, Params()))
    assert "<script" not in html and "&lt;script&gt;" in html


def test_gain_cli_flag_is_validated(tmp_path):
    with pytest.raises(SystemExit):
        main(["analyse", "--max-gain-share", "2"])
