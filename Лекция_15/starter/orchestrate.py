"""Оркестратор: четыре читателя, сборщик, критик (лекция 15, слайды 14, 16, 21–25).

Читают многие, пишет один: chart_write есть только у оркестратора (submit).
Стартовый код. Что дописывают студенты — в README практикума.
"""
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from spawn import CONTRACTS, ReaderTools, Span, spawn_subagent

from p0042.tools import Dispatcher, Toolbox

KNOWN = ["дата консилиума может быть спорной — дату не выбирать, каждое упоминание вернуть в board_mentions",
         "маршрут задан кафедрой — не менять",
         "диагноз не формулировать, лечение не предлагать"]

READERS = {   # имя: (цель, типы записей, документы, контракт, подпись для врача)
    "problems": ("свести проблемы: диагнозы и сопутствующие; найти упоминания даты консилиума во встречах",
                 ["Condition", "Encounter"], False, "problems_list", "проблемы"),
    "meds": ("свести принимаемые препараты", ["MedicationStatement"], False, "med_list", "лекарства"),
    "lab": ("свести маркеры HER2, ER, PR, Ki-67", ["Observation"], False, "lab_summary", "лаборатория"),
    "imaging": ("свести протоколы визуализации; найти в них упоминания даты консилиума",
                ["DocumentReference"], True, "imaging_summary", "снимок"),
}

CHECKLIST = [   # перечень кафедры для критика (слайд 24)
    "у каждого значения есть source — ссылка FHIR",
    "если дат консилиума больше одной — дата не выбрана, спор в open_questions с обеими ссылками",
    "статусы failed и partial видны в пакете",
    "в пакете нет формулировок диагноза и назначений",
    "по HER2, ER, PR, Ki-67 есть значение или запись «не найден»",
]


def task(name, case):
    goal, types, _, contract, _ = READERS[name]
    return {"goal": goal, "scope": f"{', '.join(types)} случая {case}", "case": case,
            "known": KNOWN, "output": contract, "budget": "8 оборотов · 20k токенов"}


def tools_for(name, store, case):
    _, types, docs, _, _ = READERS[name]
    return ReaderTools(store, case, types, documents=docs)


def run_readers(case, store, model, trace=None, parent="оркестратор", timeout=60, spawn=spawn_subagent):
    """Параллельно, не больше четырёх, у каждого свой таймаут. Отказ — данные, а не исключение."""
    def one(name):
        contract = CONTRACTS[READERS[name][3]]
        art = spawn(task(name, case), contract, tools_for(name, store, case), model,
                    trace=trace, name=READERS[name][4], parent=parent)
        if art.get("status") == "failed" and "оборот" in art.get("reason", ""):   # не по схеме — один повтор
            art = spawn(task(name, case), contract, tools_for(name, store, case), model,
                        trace=trace, name=READERS[name][4] + ", повтор", parent=parent)
        return art

    arts = {}
    pool = ThreadPoolExecutor(max_workers=4)
    futures = {n: pool.submit(one, n) for n in READERS}
    for n, f in futures.items():
        try:
            arts[n] = f.result(timeout=timeout)
        except FutureTimeout:
            arts[n] = {"type": READERS[n][3], "status": "failed", "reason": f"таймаут {timeout} с"}
        except Exception as e:                                   # noqa: BLE001 — сбой читателя не роняет пакет
            arts[n] = {"type": READERS[n][3], "status": "failed", "reason": f"ошибка: {e}"}
    pool.shutdown(wait=False, cancel_futures=True)
    return arts


def assemble(arts, case="P-0042"):
    """Сборщик: детерминированный код. Ничего не выбирает — споры идут в open_questions (слайд 23)."""
    pkg = {"case": case, "board_date": "не назначена", "open_questions": [], "sources": []}
    dates = {}
    for name, art in arts.items():
        label = READERS[name][4]
        if art.get("status") == "failed":
            pkg["open_questions"].append(f"{label}: читатель не ответил — {art.get('reason', 'нет причины')}")
            pkg[name] = {"status": "failed", "items": []}
            continue
        if art.get("status") == "partial":
            pkg["open_questions"].append(f"{label}: данные неполные (status partial)")
        pkg[name] = {"status": art["status"], "items": art["items"]}
        pkg["sources"] += [i["source"] for i in art["items"]]
        for m in art.get("board_mentions", []):
            dates.setdefault(m["date"], [])
            if m["source"] not in dates[m["date"]]:
                dates[m["date"]].append(m["source"])
        pkg["open_questions"] += [q for q in art.get("open", []) if q not in pkg["open_questions"]]
    if len(dates) == 1:
        pkg["board_date"] = next(iter(dates))
    elif len(dates) > 1:
        many = "две даты" if len(dates) == 2 else f"{len(dates)} даты"
        pkg["open_questions"].insert(0, f"{many} консилиума: " + " и ".join(
            f"{d} ({', '.join(src)})" for d, src in sorted(dates.items())))
    pkg["sources"] = list(dict.fromkeys(pkg["sources"]))
    return pkg


def revise(pkg, remarks):
    """Правка по замечаниям критика. В стартовом коде — ничего не меняет; это место для вашей логики."""
    return pkg


def criticize(pkg, model, trace=None, parent="оркестратор", rounds=2, spawn=spawn_subagent):
    """Чистое окно: только пакет и перечень. Не больше двух кругов, остаток — врачу как есть."""
    remarks = []
    for r in range(1, rounds + 1):
        review = spawn({"goal": "проверить пакет по перечню кафедры; пакет не переписывать",
                        "case": pkg["case"], "checklist": CHECKLIST, "package": pkg,
                        "output": "critic_review"},
                       CONTRACTS["critic_review"], None, model, max_turns=3,
                       trace=trace, name="критик" + (f", круг {r}" if r > 1 else ""), parent=parent)
        remarks = [i for i in review.get("items", []) if i["verdict"] == "remark"]
        if review.get("status") == "failed" or not remarks or r == rounds:
            break
        pkg = revise(pkg, remarks)
    pkg["critic"] = {"status": review.get("status"), "remarks": remarks}
    return pkg


def build_package(case, store, reader_model, critic_model, trace=None, timeout=60, spawn=spawn_subagent):
    root = Span(trace, "оркестратор")
    try:
        arts = run_readers(case, store, reader_model, trace, root.name, timeout, spawn)
        pkg = assemble(arts, case)
        return criticize(pkg, critic_model, trace, root.name, spawn=spawn)
    finally:
        root.end(status="ok")


def submit(pkg, store, confirm=None, trace=None):
    """Единственная запись: chart_write у оркестратора, политика «спросить» (лекция 13)."""
    dispatch = Dispatcher(Toolbox(store), confirm=confirm, trace=trace)
    return dispatch("chart_write", {"case_id": pkg["case"],
                                    "text": json.dumps(pkg, ensure_ascii=False)[:2000]})


TOOLS = {n: set(tools_for(n, None, "P-0042").registry) for n in READERS}       # для теста «пишет один»
