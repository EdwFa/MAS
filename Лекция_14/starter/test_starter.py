"""pytest -q Лекция_14/starter — стартовый код работает без модели (ScriptedLLM)."""
import json
import pathlib

import pytest

from bench import ASK, agent, bench_triggers, score, triggered
from skills import HERE, Sandbox, catalog, read_skill, run_script, scan, validate

from p0042.llm import ScriptedLLM
from p0042.trace import Trace

CASES = HERE / "tests" / "cases"


def act(tool=None, final=None, **args):
    return json.dumps({"final": final} if final else {"tool": tool, "args": args}, ensure_ascii=False)


def test_scan_and_catalog():
    s = scan()
    assert set(s) == {"package-check", "package-build", "lab-summary"}
    cat = catalog(s)
    assert cat.count("\n- ") == 3 and "проверь пакет" in cat
    assert "## Шаги" in read_skill(s, "package-check")
    assert read_skill(s, "нет-такого").startswith("нет скилла")


@pytest.mark.parametrize("case", sorted(p.name for p in CASES.iterdir()))
def test_check_script_matches_expected(case, tmp_path):
    pkg = json.loads((CASES / case / "package.json").read_text(encoding="utf-8"))
    exp = json.loads((CASES / case / "expected.json").read_text(encoding="utf-8"))
    box = Sandbox(tmp_path, "P-0042")
    box.put("work/package.json", pkg)
    out = run_script(scan(), box, "package-check", "scripts/check.py", "work/package.json")
    assert out["result"]["ok"] == (exp["verdict"] == "ok")
    assert out["exit_code"] == (0 if exp["verdict"] == "ok" else 1)


@pytest.mark.parametrize("name", ["-pdf", "pdf-", "pdf--check", "PDF", "claude-helper", "x" * 65])
def test_validate_rejects_bad_name(name):
    assert validate({"name": name, "description": "Проверяет."}, name)


def test_validate_rejects_xml_and_mismatch():
    assert validate({"name": "package-check", "description": "<b>x</b>"}, "package-check")
    assert validate({"name": "package-check", "description": "Проверяет."}, "other")
    assert validate({"name": "package-check", "description": "Проверяет."}, "package-check") == []


def test_check_script_errors_are_json(tmp_path):
    box = Sandbox(tmp_path, "P-0042")
    (box.dir / "work" / "package.json").write_text("{не json", encoding="utf-8")
    out = run_script(scan(), box, "package-check", "scripts/check.py", "work/package.json")
    assert out["exit_code"] == 2 and out["result"]["ok"] is False and "error" in out["result"]


def test_sandbox_blocks_escape(tmp_path):
    box = Sandbox(tmp_path, "P-0042")
    box.put("work/package.json", {})
    s = scan()
    assert run_script(s, box, "package-check", "../package-build/SKILL.md", "work/package.json")["isError"]
    assert run_script(s, box, "package-check", "scripts/check.py", "../../../etc/passwd")["isError"]


def test_skill_in_trace_like_slide_16(tmp_path):
    """read_skill → run_script → final: трасса как на слайде 18."""
    pkg = json.loads((CASES / "02_no_histology" / "package.json").read_text(encoding="utf-8"))
    llm = ScriptedLLM([
        act("read_skill", name="package-check"),
        act("run_script", skill="package-check", script="scripts/check.py", file="work/package.json"),
        act(final={"answer": "В пакете нет ссылки на гистологию (histology_ref).", "sources": [],
                   "open_questions": [], "verdict": "problems"}),
    ])
    t = Trace()
    res = agent(ASK.format(case="P-0042", package=json.dumps(pkg), question="Проверь пакет"),
                "P-0042", llm, t, package=pkg, workdir=tmp_path)
    tools = t.of("tool")
    assert [e["name"] for e in tools] == ["read_skill", "run_script"]
    assert tools[1]["result"]["result"] == {"ok": False, "problems": ["нет поля histology_ref"]}
    assert tools[1]["result"]["sandbox"] == "cases/P-0042/"
    assert "Скиллы." in llm.prompts[0][0]["content"]          # каталог в правилах
    assert score(res, json.loads((CASES / "02_no_histology" / "expected.json").read_text(encoding="utf-8")))


def test_without_skills_no_skill_tools(tmp_path):
    llm = ScriptedLLM([act("read_skill", name="package-check")])
    t = Trace()
    agent("Проверь пакет P-0042", "P-0042", llm, t, with_skills=False, max_steps=1, workdir=tmp_path)
    assert t.of("tool")[0]["result"]["isError"] and not triggered(t)
    assert "Скиллы." not in llm.prompts[0][0]["content"]


def test_trigger_bench_counts(tmp_path):
    csv = tmp_path / "t.csv"
    csv.write_text("id,phrase,expected,why\ny,Проверь пакет,да,\nn,Собери пакет,нет,\n", encoding="utf-8")
    llm = ScriptedLLM([act("read_skill", name="package-check")] * 2 + [act("read_skill", name="package-check")]
                      + [act("read_skill", name="package-build")] * 3)
    rows, yes, no = bench_triggers(llm, csv, runs=3, out=tmp_path)
    assert [r["hits"] for r in rows] == [3, 0] and yes == 1.0 and no == 1.0


def test_score_two_dates():
    exp = json.loads((CASES / "03_two_dates" / "expected.json").read_text(encoding="utf-8"))
    good = {"verdict": "problems", "answer": "", "open_questions": ["дата консилиума: 20.11 или 27.11"]}
    picked = {"verdict": "ok", "answer": "консилиум 20.11", "open_questions": []}
    assert score(good, exp) and not score(picked, exp)
