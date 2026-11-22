"""Тесты срабатывания и тесты работы скилла (лекция 14, слайды 21 и 22).

    python bench.py triggers      # tests/triggers.csv × RUNS прогонов → triggers_report.md
    python bench.py work          # tests/cases/*  без скилла и со скиллом → work_report.md

Модель — локальная (P0042_BASE_URL, P0042_MODEL), как в run.py каркаса.
Трассы прогонов — в traces/.
"""
import csv
import json
import pathlib
import sys
import tempfile

from skills import HERE, SkillToolbox, Sandbox, catalog, scan

from p0042.fhir import FHIRStore
from p0042.harness import run
from p0042.tools import Dispatcher
from p0042.trace import Trace

RUNS = 3
SKILL = "package-check"
ASK = ('Пакет к консилиуму по случаю {case}:\n{package}\n\n{question}\n'
       'В final добавь поле verdict: "ok", если пакет готов, или "problems", если нет.')


def agent(question, case_id, llm, trace, with_skills=True, package=None, max_steps=6, workdir=None):
    """Один прогон агента P-0042 со скиллами или без. package кладётся в work/package.json песочницы."""
    skills = scan() if with_skills else {}
    box = Sandbox(workdir or tempfile.mkdtemp(prefix="p0042-"), case_id)
    if package is not None:
        box.put("work/package.json", package)
    dispatch = Dispatcher(SkillToolbox(FHIRStore(), skills=skills, sandbox=box), trace=trace)
    try:
        return run(question, case_id, llm, dispatch, trace, max_steps=max_steps,
                   rules=catalog(skills) if skills else "")
    finally:
        box.clear()


def triggered(trace):
    """Скилл сработал, если модель прочитала именно его."""
    return any(e["name"] == "read_skill" and e["args"].get("name") == SKILL
               and not e["result"].get("isError") for e in trace.of("tool"))


def bench_triggers(llm, path=HERE / "tests" / "triggers.csv", runs=RUNS, out=HERE / "traces"):
    out.mkdir(exist_ok=True)
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        hits = 0
        for i in range(runs):
            t = Trace(out / "triggers.jsonl", run_id=f"trg-{r['id']}-{i}")
            agent(r["phrase"], "P-0042", llm, t, max_steps=1)      # нужен только первый ход
            hits += triggered(t)
        rows.append({**r, "hits": hits, "runs": runs})
    yes = [x for x in rows if x["expected"] == "да"]
    no = [x for x in rows if x["expected"] == "нет"]
    share = lambda xs, want: sum((x["hits"] if want else x["runs"] - x["hits"]) for x in xs) / max(1, sum(x["runs"] for x in xs))
    return rows, share(yes, True), share(no, False)


def score(result, expected):
    """Ответ агента против ожидаемого: verdict и обязательные упоминания (каждое — список синонимов)."""
    text = (str(result.get("answer") or "") + " " + " ".join(map(str, result.get("open_questions", [])))).lower()
    ok = result.get("verdict") == expected["verdict"]
    ok &= all(any(s.lower() in text for s in alts) for alts in expected.get("must_mention", []))
    oq = " ".join(map(str, result.get("open_questions", []))).lower()
    ok &= all(any(s.lower() in oq for s in alts) for alts in expected.get("open_questions_must", []))
    return bool(ok)


def bench_work(llm, cases=HERE / "tests" / "cases", out=HERE / "traces"):
    out.mkdir(exist_ok=True)
    rows = []
    for d in sorted(p for p in cases.iterdir() if p.is_dir()):
        pkg = json.loads((d / "package.json").read_text(encoding="utf-8"))
        exp = json.loads((d / "expected.json").read_text(encoding="utf-8"))
        q = ASK.format(case=pkg.get("case_id", "P-0042"), package=json.dumps(pkg, ensure_ascii=False),
                       question=exp.get("question", "Проверь пакет к консилиуму."))
        row = {"case": d.name, "expected": exp["note"]}
        for label, with_skills in (("без скилла", False), ("со скиллом", True)):
            t = Trace(out / "work.jsonl", run_id=f"work-{d.name}-{'s' if with_skills else 'n'}")
            res = agent(q, pkg.get("case_id", "P-0042"), llm, t, with_skills=with_skills, package=pkg)
            row[label] = score(res, exp)
        rows.append(row)
    return rows


def main():
    from p0042.llm import LocalLLM
    llm = LocalLLM()
    what = sys.argv[1] if len(sys.argv) > 1 else "triggers"
    if what == "triggers":
        rows, yes, no = bench_triggers(llm)
        md = ["| Фраза | Должен | Сработал |", "| --- | --- | --- |"]
        md += [f"| {r['phrase']} | {r['expected']} | {r['hits']}/{r['runs']} |" for r in rows]
        md += ["", f"Доля «да», где скилл сработал: **{yes:.2f}**",
               f"Доля «нет», где скилл не сработал: **{no:.2f}**"]
        (HERE / "triggers_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    else:
        rows = bench_work(llm)
        mark = lambda b: "✓" if b else "✗"
        md = ["| Пакет | Ожидаемо | Без скилла | Со скиллом |", "| --- | --- | --- | --- |"]
        md += [f"| {r['case']} | {r['expected']} | {mark(r['без скилла'])} | {mark(r['со скиллом'])} |" for r in rows]
        md += ["", f"Без скилла: {sum(r['без скилла'] for r in rows)}/{len(rows)}; "
                   f"со скиллом: {sum(r['со скиллом'] for r in rows)}/{len(rows)}"]
        (HERE / "work_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
