"""pytest -q Лекция_15/starter — код между агентами на заглушках, без модели (слайд 21)."""
import json
import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from orchestrate import READERS, TOOLS, assemble, build_package, criticize, run_readers, submit, task  # noqa: E402
from spawn import CONTRACTS, HERE, ReaderTools, spawn_subagent, tree  # noqa: E402

from p0042.fhir import FHIRStore  # noqa: E402
from p0042.trace import Trace  # noqa: E402

CON = {n: CONTRACTS[READERS[n][3]] for n in READERS}


def fixture(name):
    return json.loads((HERE / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))


def stub(name):
    """Заглушка вместо модели: сразу возвращает готовый артефакт."""
    text = json.dumps(fixture(name), ensure_ascii=False)
    return lambda window: text


def by_reader(window):
    """Одна заглушка на всех читателей: отвечает по типу артефакта из задачи."""
    out = json.loads(window[1]["content"])["output"]
    name = {"problems_list": "problems", "med_list": "meds", "lab_summary": "lab",
            "imaging_summary": "imaging", "critic_review": "critic_ok"}[out]
    return json.dumps(fixture(name), ensure_ascii=False)


@pytest.fixture(scope="module")
def store():
    return FHIRStore()


# --- слайд 21 ----------------------------------------------------------------

def test_board_date_survives_handoff():
    arts = {n: spawn_subagent(task(n, "P-0042"), CON[n], None, stub(n)) for n in READERS}
    pkg = assemble(arts)
    assert pkg["board_date"] is not None, "дата потеряна"
    assert pkg["board_date"] == "не назначена"                  # сборщик не выбирает
    q = pkg["open_questions"][0]
    assert "две даты" in q and "Encounter/enc-31" in q and "DocumentReference/ct-117" in q


def test_bad_artifact_is_rejected():
    art = spawn_subagent(task("lab", "P-0042"), CON["lab"], None, stub("lab_without_source"))
    assert art["status"] == "failed" and "оборот" in art["reason"]


def test_only_orchestrator_writes():
    assert all("chart_write" not in TOOLS[n] for n in READERS)


# --- схема как фильтр: слайд 18 ---------------------------------------------

@pytest.mark.parametrize("bad", ["lab_injection", "lab_with_advice"])
def test_schema_filters(bad):
    assert spawn_subagent(task("lab", "P-0042"), CON["lab"], None, stub(bad), max_turns=2)["status"] == "failed"


def test_schema_error_goes_back_to_subagent():
    replies = iter([json.dumps(fixture("lab_without_source")), json.dumps(fixture("lab"))])
    t = Trace()
    art = spawn_subagent(task("lab", "P-0042"), CON["lab"], None, lambda w: next(replies), trace=t, name="лаборатория")
    assert art["status"] == "ok" and len(t.of("schema_error")) == 1


# --- субагент с инструментами: свой цикл и свои права ----------------------

def test_reader_uses_only_its_tools(store):
    replies = iter([
        '{"tool": "fhir_search", "args": {"type": "MedicationStatement"}}',      # чужой тип
        '{"tool": "chart_write", "args": {"case_id": "P-0042", "text": "x"}}',   # нет в реестре
        '{"tool": "fhir_search", "args": {"type": "Observation"}}',
        json.dumps(fixture("lab")),
    ])
    t = Trace()
    art = spawn_subagent(task("lab", "P-0042"), CON["lab"], ReaderTools(store, "P-0042", ["Observation"]),
                         lambda w: next(replies), trace=t, name="лаборатория")
    calls = t.of("tool")
    assert calls[0]["result"]["isError"] and "вне задачи" in calls[0]["result"]["text"]
    assert calls[1]["result"]["isError"] and "нет инструмента" in calls[1]["result"]["text"]
    assert any(r["ref"] == "Observation/her2-77" for r in calls[2]["result"]["result"])
    assert art["status"] == "ok"


# --- отказы: слайд 22 -------------------------------------------------------

def test_timeout_one_reader(store):
    def slow_lab(window):
        if json.loads(window[1]["content"])["output"] == "lab_summary":
            time.sleep(1.0)
        return by_reader(window)
    arts = run_readers("P-0042", store, slow_lab, timeout=0.3)
    pkg = assemble(arts)
    assert arts["lab"]["status"] == "failed" and pkg["lab"]["status"] == "failed"
    assert any(q.startswith("лаборатория: читатель не ответил") and "таймаут" in q for q in pkg["open_questions"])
    assert pkg["meds"]["status"] == "ok"                          # остальные собраны


def test_partial_is_visible():
    arts = {n: spawn_subagent(task(n, "P-0042"), CON[n], None, stub(n)) for n in READERS}
    pkg = assemble(arts)
    assert pkg["imaging"]["status"] == "partial"
    assert any("снимок: данные неполные" in q for q in pkg["open_questions"])
    assert "Ki-67 не найден" in pkg["open_questions"]


# --- критик и граф целиком --------------------------------------------------

def test_critic_clean_window_and_two_rounds():
    seen = []

    def critic(window):
        seen.append(json.loads(window[1]["content"]))
        return json.dumps(fixture("critic_remark"), ensure_ascii=False)
    pkg = assemble({n: spawn_subagent(task(n, "P-0042"), CON[n], None, stub(n)) for n in READERS})
    out = criticize(pkg, critic, rounds=2)
    assert len(seen) == 2                                         # предел — два круга
    assert set(seen[0]) == {"goal", "case", "checklist", "package", "output", "output_schema", "tools"}
    assert out["critic"]["remarks"][0]["field"] == "imaging.status"   # остаток — врачу


def test_whole_graph_and_tree(store):
    t = Trace()
    pkg = build_package("P-0042", store, by_reader, by_reader, trace=t)
    assert pkg["critic"]["remarks"] == [] and "две даты" in pkg["open_questions"][0]
    text = tree(t)
    assert text.splitlines()[0].startswith("оркестратор")
    for label in ("· проблемы", "· лекарства", "· лаборатория", "· снимок", "· критик"):
        assert label in text


def test_write_waits_for_doctor(store):
    pkg = assemble({n: spawn_subagent(task(n, "P-0042"), CON[n], None, stub(n)) for n in READERS})
    assert submit(pkg, store)["status"] == "waiting_doctor"
    assert submit(pkg, store, confirm=lambda n, a: True)["status"] == "written"


def test_bench_runs_on_stubs(tmp_path):
    """Стенд замера собирается и считает три строки — на заглушках, без модели."""
    import measure

    def factory():
        state = {"n": 0}

        def model(window):
            if window[0]["content"].startswith("Ты субагент"):
                return by_reader(window)
            state["n"] += 1                                     # одиночный агент: сразу final
            return json.dumps({"final": {"answer": "HER2 3+, Ki-67 не найден, даты 20.11 и 27.11, метформин",
                                         "sources": [], "open_questions": []}}, ensure_ascii=False)
        return model
    rows = measure.bench(factory, out=tmp_path)
    assert [r["тесты работы"] for r in rows] == ["1 из 1"] * 3
    assert rows[2]["токены, тыс."] > 0 and (tmp_path / "tree-P-0042.txt").exists()
