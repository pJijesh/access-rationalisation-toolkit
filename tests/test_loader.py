import pytest

from access_rat.cli import main
from access_rat.errors import ValidationError
from access_rat.loader import load_dataset


def write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def files(tmp_path):
    return {
        "users": write(tmp_path / "users.csv", "user,department,job_title\nu1,Ops,Clerk\nu2,Ops,Clerk\n"),
        "memberships": write(tmp_path / "memberships.csv", "user,group\nu1,G1\nu2,G1\nu2,G2\n"),
        "perms": write(tmp_path / "group_permissions.csv", "group,permission\nG1,a.view\nG2,a.edit\n"),
        "sod": write(tmp_path / "sod_rules.csv", "permission_a,permission_b\na.view,a.edit\n"),
    }


def load(f, sod=True):
    return load_dataset(f["users"], f["memberships"], f["perms"], f["sod"] if sod else None)


def test_valid_input_loads(files):
    ds = load(files)
    assert sorted(ds.users) == ["u1", "u2"]
    assert ds.group_members["G1"] == {"u1", "u2"}
    assert ds.sod_rules[0].rule_id == "SOD-001"  # generated when the column is absent
    assert set(ds.input_hashes) == {"users.csv", "memberships.csv", "group_permissions.csv", "sod_rules.csv"}


def test_headers_are_case_insensitive_and_bom_tolerant(files):
    write(files["users"], "﻿User, Department ,JOB_TITLE\nu1,Ops,Clerk\nu2,Ops,Clerk\n")
    assert len(load(files).users) == 2


def test_missing_required_column(files):
    write(files["memberships"], "user,team\nu1,G1\n")
    with pytest.raises(ValidationError) as exc:
        load(files)
    assert "missing required column(s): group" in exc.value.problems[0]


def test_missing_file(files, tmp_path):
    files["perms"] = tmp_path / "nope.csv"
    with pytest.raises(ValidationError) as exc:
        load(files)
    assert "file not found" in exc.value.problems[0]


def test_empty_file_is_reported(files):
    write(files["users"], "")
    with pytest.raises(ValidationError) as exc:
        load(files)
    assert any("file is empty" in p for p in exc.value.problems)


def test_duplicate_user_with_line_number(files):
    write(files["users"], "user,department,job_title\nu1,Ops,Clerk\nu1,Ops,Clerk\nu2,Ops,Clerk\n")
    with pytest.raises(ValidationError) as exc:
        load(files)
    assert "users.csv line 3: duplicate user 'u1'" in exc.value.problems


def test_membership_for_unknown_user(files):
    write(files["memberships"], "user,group\nu1,G1\nghost,G1\n")
    with pytest.raises(ValidationError) as exc:
        load(files)
    assert "ghost" in exc.value.problems[0] and "line 3" in exc.value.problems[0]


def test_empty_value_reported(files):
    write(files["perms"], "group,permission\nG1,\n")
    with pytest.raises(ValidationError) as exc:
        load(files)
    assert "empty value for permission" in exc.value.problems[0]


def test_sod_rule_with_identical_sides_and_duplicate_id(files):
    write(files["sod"], "rule_id,permission_a,permission_b\nR1,a.view,a.view\nR2,a.view,a.edit\nR2,a.edit,a.view\n")
    with pytest.raises(ValidationError) as exc:
        load(files)
    joined = " ".join(exc.value.problems)
    assert "identical" in joined and "duplicate rule_id 'R2'" in joined


def test_all_problems_are_collected_in_one_pass(files):
    write(files["users"], "user,department\nu1,Ops\n")
    write(files["memberships"], "user,group\nu1,\n")
    with pytest.raises(ValidationError) as exc:
        load(files)
    assert len(exc.value.problems) >= 2


def test_duplicate_rows_are_warnings_not_errors(files):
    write(files["memberships"], "user,group\nu1,G1\nu1,G1\nu2,G1\n")
    ds = load(files)
    assert any("duplicate membership" in w for w in ds.warnings)
    assert ds.group_members["G1"] == {"u1", "u2"}


def test_sod_permission_unknown_to_any_group_is_a_warning(files):
    write(files["sod"], "permission_a,permission_b\na.view,zzz.nothing\n")
    assert any("zzz.nothing" in w for w in load(files).warnings)


def test_group_with_members_but_no_permissions_is_allowed(files):
    write(files["memberships"], "user,group\nu1,G1\nu2,G_NOPERMS\n")
    ds = load(files)
    assert "G_NOPERMS" in ds.groups and ds.perms_of("G_NOPERMS") == frozenset()


def test_cli_exits_2_and_prints_problems(files, tmp_path, capsys):
    write(files["memberships"], "user,group\nghost,G1\n")
    code = main(["analyse", "--data", str(tmp_path), "--out", str(tmp_path / "out")])
    assert code == 2
    err = capsys.readouterr().err
    assert "Input validation failed" in err and "ghost" in err
    assert not (tmp_path / "out").exists()
