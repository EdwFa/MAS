"""pytest -q Лекция_14/examples — второй учебный скилл: hn-staging-check (голова и шея)."""
import json
import pathlib
import subprocess
import sys

import pytest
import yaml

SKILL = pathlib.Path(__file__).resolve().parents[1] / "hn-staging-check"
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL.parents[1] / "starter"))

from stage import stage  # noqa: E402
from skills import validate  # noqa: E402


def st(site, t, n, m, **kw):
    out, code = stage({"site": site, "T": t, "N": n, "M": m, **kw})
    return out.get("stage"), code


# общая группировка AJCC 8 — по строке на каждую строку таблицы (раздел 1)
@pytest.mark.parametrize("t,n,m,exp", [
    ("Tis", "N0", "M0", "0"), ("T1", "N0", "M0", "I"), ("T2", "N0", "M0", "II"),
    ("T3", "N0", "M0", "III"), ("T2", "N1", "M0", "III"), ("T4a", "N1", "M0", "IVA"),
    ("T1", "N2b", "M0", "IVA"), ("T2", "N3a", "M0", "IVB"), ("T4b", "N0", "M0", "IVB"),
    ("T1", "N0", "M1", "IVC"), ("pT3", "pN1", "cM0", "III")])
def test_common_grouping(t, n, m, exp):
    assert st("oral_cavity", t, n, m)[0] == exp
    assert st("larynx", t, n, m)[0] == exp


@pytest.mark.parametrize("t,n,m,exp", [
    ("T0", "N1", "M0", "I"), ("T2", "N1", "M0", "I"), ("T1", "N2", "M0", "II"),
    ("T3", "N2", "M0", "II"), ("T1", "N3", "M0", "III"), ("T4", "N0", "M0", "III"), ("T2", "N1", "M1", "IV")])
def test_oropharynx_p16_clinical(t, n, m, exp):
    assert st("oropharynx", t, n, m, p16="positive", basis="clinical")[0] == exp


@pytest.mark.parametrize("t,n,m,exp", [
    ("T2", "N1", "M0", "I"), ("T1", "N2", "M0", "II"), ("T4", "N1", "M0", "II"),
    ("T3", "N2", "M0", "III"), ("T1", "N0", "M1", "IV")])
def test_oropharynx_p16_pathological(t, n, m, exp):
    assert st("oropharynx", t, n, m, p16="positive", basis="pathological")[0] == exp


@pytest.mark.parametrize("t,n,m,exp", [
    ("T1", "N0", "M0", "IA"), ("T2", "N1", "M0", "IB"), ("T3", "N0", "M0", "II"),
    ("T2", "N2", "M0", "II"), ("T4", "N1", "M0", "III"), ("T1", "N3", "M0", "III"),
    ("T2", "N1", "M1a", "IVA"), ("T2", "N1", "M1b", "IVB")])
def test_nasopharynx_v9(t, n, m, exp):
    assert st("nasopharynx", t, n, m)[0] == exp


def test_same_tnm_differs_by_p16():
    """T2N2M0: IVA при p16−, II при p16+ — поэтому p16 обязателен для ротоглотки."""
    assert st("oropharynx", "T2", "N2", "M0", p16="negative")[0] == "IVA"
    assert st("oropharynx", "T2", "N2", "M0", p16="positive", basis="clinical")[0] == "II"


def test_unknown_p16_uses_negative_table_with_note():
    out, _ = stage({"site": "oropharynx", "T": "T2", "N": "N1", "M": "M0"})
    assert out["stage"] == "III" and "p16 неизвестен" in out["notes"][0]


def test_documented_stage_match_and_mismatch():
    assert stage({"site": "larynx", "T": "T3", "N": "N0", "M": "M0", "documented_stage": "III"})[1] == 0
    out, code = stage({"site": "larynx", "T": "T3", "N": "N1", "M": "M0", "documented_stage": "стадия II"})
    assert code == 1 and out["stage"] == "III" and out["documented"] == "II"


@pytest.mark.parametrize("data", [
    {"site": "larynx", "T": "T4", "N": "N0", "M": "M0"},             # нужна подкатегория T4a/T4b
    {"site": "nasopharynx", "T": "T2", "N": "N0", "M": "M1"},        # нужен M1a/M1b
    {"site": "oropharynx", "T": "T3", "N": "N3", "M": "M0", "p16": "positive", "basis": "pathological"},
    {"site": "thyroid", "T": "T1", "N": "N0", "M": "M0"},
    {"site": "larynx", "T": "T9", "N": "N0", "M": "M0"},
    {"site": "larynx", "N": "N0", "M": "M0"}])
def test_cannot_stage_is_code_2(data):
    out, code = stage(data)
    assert code == 2 and out["ok"] is False and out["error"]


def test_script_cli_errors_are_json(tmp_path):
    bad = tmp_path / "staging.json"
    bad.write_text("{не json", encoding="utf-8")
    p = subprocess.run([sys.executable, "-I", str(SKILL / "scripts" / "stage.py"), str(bad)],
                       capture_output=True, text=True)
    assert p.returncode == 2 and json.loads(p.stdout)["ok"] is False


def test_skill_frontmatter_follows_spec():
    _, front, body = (SKILL / "SKILL.md").read_text(encoding="utf-8").split("---", 2)
    meta = yaml.safe_load(front)
    assert validate(meta, SKILL.name) == []
    assert "scripts/stage.py" in body and "references/staging_tables.md" in body
    assert len(body.splitlines()) < 500
