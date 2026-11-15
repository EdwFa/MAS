"""Замер «один против нескольких» (лекция 15, слайды 6 и 28).

    python measure.py          # cases/*.json → bench.csv и трассы в traces/

Три строки: один агент; один агент с бюджетом, равным многоагентному; оркестратор с читателями и критиком.
Та же локальная модель, те же инструменты чтения, те же случаи. Токены — оценка spawn.tokens.
"""
import csv
import json
import time

from orchestrate import build_package
from spawn import HERE, TYPES, ReaderTools, tokens, tree

from p0042.fhir import FHIRStore
from p0042.harness import run
from p0042.tools import Dispatcher
from p0042.trace import Trace

SINGLE = ("Собери пакет к консилиуму по случаю {case}: диагнозы, препараты, маркеры HER2, ER, PR, Ki-67, "
          "протоколы визуализации, дата консилиума. Каждое значение — со ссылкой на запись. "
          "Дату не выбирай: если упоминаний несколько — перечисли все в open_questions. "
          "Диагноз не формулируй, лечение не предлагай.")


class Counted:
    """Обёртка над моделью: считает токены входа и выхода."""

    def __init__(self, llm):
        self.llm, self.tokens = llm, 0

    def __call__(self, messages):
        reply = self.llm(messages)
        self.tokens += tokens(json.dumps(messages, ensure_ascii=False)) + tokens(reply)
        return reply


def passed(output, case):
    text = json.dumps(output, ensure_ascii=False).lower()
    return all(any(s.lower() in text for s in alts) for alts in case["must_mention"])


def single(case, llm, max_steps, trace):
    box = ReaderTools(FHIRStore(), case["case"], TYPES, documents=True)
    return run(SINGLE.format(case=case["case"]), case["case"], llm, Dispatcher(box, trace=trace), trace,
               max_steps=max_steps)


def bench(llm_factory, budget_steps=20, out=HERE / "traces"):
    out.mkdir(exist_ok=True)
    rows = {k: {"устройство": k, "тесты работы": 0, "токены, тыс.": 0.0, "время, с": 0.0}
            for k in ("один агент", "один агент, равный бюджет", "оркестратор, 4 читателя, критик")}
    cases = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((HERE / "cases").glob("*.json"))]
    for case in cases:
        for key, steps in (("один агент", 8), ("один агент, равный бюджет", budget_steps)):
            llm, t, t0 = Counted(llm_factory()), Trace(out / "single.jsonl", run_id=f"{case['case']}-{steps}"), time.monotonic()
            res = single(case, llm, steps, t)
            rows[key]["тесты работы"] += passed(res, case)
            rows[key]["токены, тыс."] += llm.tokens / 1000
            rows[key]["время, с"] += time.monotonic() - t0
        key = "оркестратор, 4 читателя, критик"
        llm, t, t0 = Counted(llm_factory()), Trace(out / "multi.jsonl", run_id=f"{case['case']}-multi"), time.monotonic()
        pkg = build_package(case["case"], FHIRStore(), llm, llm, trace=t)
        rows[key]["тесты работы"] += passed(pkg, case)
        rows[key]["токены, тыс."] += llm.tokens / 1000
        rows[key]["время, с"] += time.monotonic() - t0
        (out / f"tree-{case['case']}.txt").write_text(tree(t) + "\n", encoding="utf-8")
    for r in rows.values():
        r["тесты работы"] = f'{r["тесты работы"]} из {len(cases)}'
        r["токены, тыс."] = round(r["токены, тыс."], 1)
        r["время, с"] = round(r["время, с"], 1)
    return list(rows.values())


def main():
    from p0042.llm import LocalLLM
    rows = bench(LocalLLM)
    with open(HERE / "bench.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(" | ".join(str(v) for v in r.values()))


if __name__ == "__main__":
    main()
