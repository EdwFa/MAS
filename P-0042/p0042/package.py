"""Детерминированный пакет к консилиуму — без модели (лекции 13, 18).

Нужен для двух вещей: интерфейс врача работает без локальной модели, а тихий режим
получает «базовый» пакет, с которым сравнивают агента. Агент на модели должен
быть не хуже этого пакета, иначе модель в системе не нужна.
"""
import re
from datetime import date

from .calc import CalcError, egfr

BOARD_IN_TEXT = re.compile(r"консилиум\w*\s+(\d{2}\.\d{2})", re.I)


def _age(birth, as_of):
    b, d = date.fromisoformat(birth), date.fromisoformat(as_of)
    return d.year - b.year - ((d.month, d.day) < (b.month, b.day))


def _ddmm(iso):
    return f"{iso[8:10]}.{iso[5:7]}"


def board_dates(store, case_id):
    """Все даты консилиума, которые встречаются в карте, с источниками."""
    found = {}
    for e in store.search("Encounter", case_id):
        if "консилиум" in e["type"][0]["text"].lower():
            found.setdefault(_ddmm(e["period"]["start"]), []).append(store.ref(e))
    for d in store.search("DocumentReference", case_id):
        for m in BOARD_IN_TEXT.finditer(store.document_text(d["id"])):
            found.setdefault(m.group(1), []).append(store.ref(d))
    return found


def build_package(store, index, case_id, as_of):
    secs, open_q = [], []

    def section(title, items):
        if items:
            secs.append({"title": title, "items": items})

    def item(text, ref, status="ok"):
        return {"text": text, "source": ref, "status": status}

    patient = store.read("Patient", case_id)
    age = _age(patient["birthDate"], as_of)
    conds = store.search("Condition", case_id)
    confirmed = [c for c in conds if c["verificationStatus"] == "confirmed"]
    onco = [c for c in conds if c["code"].get("coding", [{}])[0].get("code", "").startswith("C")]
    onco_conf = [c for c in onco if c["verificationStatus"] == "confirmed"]
    shown = onco_conf or onco
    section("Диагноз", [item(c["code"]["text"], store.ref(c),
                             "ok" if c in onco_conf else "предварительный") for c in shown])
    if onco and not onco_conf:
        open_q.append("диагноз предварительный — нужна верификация")
    section("Сопутствующие", [item(c["code"]["text"], store.ref(c)) for c in confirmed if c not in onco])

    markers = [o for o in store.search("Observation", case_id)
               if o.get("category", [{}])[0].get("text") in ("pathology", "staging")]
    section("Опухоль", [item(f'{o["code"]["text"]}: {o.get("valueString") or o.get("valueQuantity", {}).get("value")}',
                             store.ref(o)) for o in markers])
    breast = any(c["code"].get("coding", [{}])[0].get("code", "").startswith("C50") for c in onco)
    if breast and not any("ki-67" in o["code"]["text"].lower() for o in markers):
        open_q.append("Ki-67 не выполнен")
    her2 = [o for o in markers if o["code"]["text"].startswith("HER2") and o.get("valueString") == "2+"]
    if her2:
        open_q.append("HER2 2+ — нужен ISH")

    renal = []
    crea = store.latest(case_id, "креатинин")
    if crea is None:
        open_q.append("нет креатинина: СКФ не рассчитана")
    else:
        q = crea["valueQuantity"]
        renal.append(item(f'Креатинин {q["value"]} {q["unit"]} от {_ddmm(crea["effectiveDateTime"])}', store.ref(crea)))
        try:
            r = egfr("female" if patient["gender"] == "female" else "male", age, q["value"], q["unit"])
            renal.append(item(f'СКФ {r["egfr"]} {r["unit"]}, {r["kdigo"]} (CKD-EPI 2021)', store.ref(crea)))
            no_ckd = not any(c["code"].get("coding", [{}])[0].get("code", "").startswith("N18") for c in conds)
            if r["egfr"] < 60 and no_ckd:
                open_q.append(f'СКФ {r["egfr"]} без диагноза ХБП: длительность снижения не подтверждена')
            meds = [m for m in store.search("MedicationStatement", case_id)
                    if "метформин" in m["medication"]["concept"]["text"].lower()]
            if r["egfr"] < 45 and meds:
                open_q.append("метформин при СКФ < 45 — вопрос к терапевту")
        except CalcError as e:
            renal.append(item(f"СКФ не рассчитана: {e}", store.ref(crea), "не проверено"))
    section("Почки", renal)

    state = []
    for test in ("гемоглобин", "масса тела", "ecog"):
        o = store.latest(case_id, test)
        if o:
            v = o.get("valueQuantity", {}).get("value", o.get("valueInteger"))
            note = (o.get("note") or [{}])[0].get("text", "")
            state.append(item(f'{o["code"]["text"]}: {v}' + (f" — {note}" if note else ""), store.ref(o)))
    section("Состояние и анализы", state)

    lvef = store.latest(case_id, "фракция выброса")
    if lvef:
        section("Сердце", [item(f'ФВ ЛЖ {lvef["valueQuantity"]["value"]}%', store.ref(lvef))])
    section("Консультации", [item(f'{d["description"]} ({_ddmm(d["date"])})', store.ref(d))
                             for d in store.search("DocumentReference", case_id) if d["type"]["text"] == "Консультация"])
    section("Семейный анамнез", [item(f'{f["relationship"]["text"]}: {f["condition"][0]["code"]["text"]}', store.ref(f))
                                 for f in store.search("FamilyMemberHistory", case_id)])
    section("Аллергии", [item(a["code"]["text"], store.ref(a)) for a in store.search("AllergyIntolerance", case_id)])
    section("Препараты", [item(m["medication"]["concept"]["text"], store.ref(m))
                          for m in store.search("MedicationStatement", case_id)])

    ext = []
    for sr in store.search("ServiceRequest", case_id):
        if sr["status"] == "active":
            ext.append(item(f'{sr["code"]["text"]}: ожидается', store.ref(sr), "не проверено"))
    for dr in store.search("DiagnosticReport", case_id):
        ext.append(item(f'{dr["code"]["text"]}: {dr["conclusion"]}', store.ref(dr)))
    section("Внешние исследования", ext)

    docs = [d for d in store.search("DocumentReference", case_id) if d["type"]["text"] == "Протокол исследования"]
    section("Протоколы", [item(f'{d["description"]} ({_ddmm(d["date"])})', store.ref(d)) for d in docs])

    dates = board_dates(store, case_id)
    if len(dates) > 1:
        open_q.append("дата консилиума: " + "; ".join(f"{k} — {', '.join(v)}" for k, v in sorted(dates.items())))
    board = next(iter(dates)) if len(dates) == 1 else "не назначена"
    section("Консилиум", [item(f"{d}: {', '.join(refs)}", refs[0], "ok" if len(dates) == 1 else "спор")
                          for d, refs in sorted(dates.items())]
            + [item(f"{d}", r, "спор") for d, refs in sorted(dates.items()) for r in refs[1:]])

    if index is not None and onco:
        queries = ["обсуждение плана на консилиуме до начала терапии", "оценка функции почек по СКФ перед системной терапией"]
        if breast:
            queries += ["анти-HER2 терапия при HER2 3+", "контроль функции сердца при анти-HER2 терапии",
                        "сниженная функция почек коррекция доз"]
        guide = []
        for qtext in queries:
            for c in index.answer_context(qtext)[:1]:
                if c["id"] not in [g["source"] for g in guide]:
                    guide.append(item(c["text"][:160] + ("…" if len(c["text"]) > 160 else ""), c["id"],
                                      "ok" if c.get("graded") else "без УУР/УДД"))
        section("Рекомендации", guide)

    sources = [i["source"] for s in secs for i in s["items"]]
    return {"case": case_id, "as_of": as_of, "board_date": board, "sections": secs,
            "open_questions": open_q, "sources": list(dict.fromkeys(sources)),
            "purpose": "Справка к консилиуму. Не ставит диагноз и не назначает лечение."}
