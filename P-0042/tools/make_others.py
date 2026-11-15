"""Генерирует карты остальных синтетических пациентов (краевые случаи).
Запуск из папки P-0042:  python tools/make_others.py
P-0051 — второй полный случай (рак желудка), P-0063 — нет креатинина и HER2 2+,
P-0077 — 17 лет, P-0024 — однофамилица P-0042 с похожими данными (риск перепутать)."""
import json


def bundle(pid, resources):
    return {"resourceType": "Bundle", "type": "collection",
            "meta": {"tag": [{"code": "synthetic", "display": "Учебные вымышленные данные. Не реальный пациент."}]},
            "entry": [{"resource": r} for r in resources]}


def obs(pid, id, text, date, loinc=None, qty=None, unit=None, string=None, integer=None, cat="laboratory", note=None):
    r = {"resourceType": "Observation", "id": id, "status": "final", "subject": {"reference": f"Patient/{pid}"},
         "category": [{"text": cat}], "code": {"text": text}, "effectiveDateTime": date}
    if loinc:
        r["code"]["coding"] = [{"system": "LOINC", "code": loinc}]
    if qty is not None:
        r["valueQuantity"] = {"value": qty, "unit": unit}
    if string is not None:
        r["valueString"] = string
    if integer is not None:
        r["valueInteger"] = integer
    if note:
        r["note"] = [{"text": note}]
    return r


def cond(pid, id, code, text, date, status="confirmed", note=None):
    r = {"resourceType": "Condition", "id": id, "subject": {"reference": f"Patient/{pid}"}, "recordedDate": date,
         "verificationStatus": status, "code": {"coding": [{"system": "ICD-10", "code": code}], "text": text}}
    if note:
        r["note"] = [{"text": note}]
    return r


def doc(pid, id, date, desc, kind):
    return {"resourceType": "DocumentReference", "id": id, "status": "current",
            "subject": {"reference": f"Patient/{pid}"}, "date": date, "type": {"text": kind}, "description": desc,
            "content": [{"attachment": {"contentType": "text/markdown", "url": f"docs/{id}.md"}}]}


def board(pid, id, date):
    return {"resourceType": "Encounter", "id": id, "subject": {"reference": f"Patient/{pid}"}, "status": "planned",
            "type": [{"text": "Онкологический консилиум"}], "period": {"start": date}}


CASES = {
 "P-0051": [
  {"resourceType": "Patient", "id": "P-0051", "gender": "male", "birthDate": "1971-08-02",
   "name": [{"text": "Орлов Д. С. (вымышленный)"}]},
  cond("P-0051", "c-90", "C16.2", "Рак тела желудка", "2026-11-05", "provisional",
       "Эндоскопически; гистология — тубулярная аденокарцинома, ИГХ HER2 в работе"),
  cond("P-0051", "c-91", "K21.0", "ГЭРБ с эзофагитом", "2019-02-11"),
  obs("P-0051", "crea-310", "Креатинин", "2026-11-06", "2160-0", 81, "umol/L"),
  obs("P-0051", "hb-310", "Гемоглобин", "2026-11-06", "718-7", 104, "g/L", note="Анемия, вероятно хроническая кровопотеря"),
  obs("P-0051", "height-51", "Рост", "2026-11-06", "8302-2", 178, "cm", cat="vital-signs"),
  obs("P-0051", "weight-51", "Масса тела", "2026-11-06", "29463-7", 69, "kg", cat="vital-signs",
      note="Потеря 6 кг за 3 месяца"),
  obs("P-0051", "ecog-51", "Статус ECOG", "2026-11-06", integer=0, cat="survey"),
  doc("P-0051", "egd-301", "2026-11-04", "ЭГДС с биопсией", "Протокол исследования"),
  doc("P-0051", "path-302", "2026-11-09", "Гистологическое исследование биопсии желудка", "Протокол исследования"),
  doc("P-0051", "ct-305", "2026-11-12", "КТ грудной клетки и брюшной полости с контрастированием", "Протокол исследования"),
  board("P-0051", "enc-51", "2026-11-20"),
 ],
 "P-0063": [
  {"resourceType": "Patient", "id": "P-0063", "gender": "female", "birthDate": "1978-01-23",
   "name": [{"text": "Лебедева Е. Н. (вымышленная)"}]},
  cond("P-0063", "c-63", "C50.9", "Рак правой молочной железы", "2026-11-11"),
  obs("P-0063", "her2-63", "HER2 (ИГХ)", "2026-11-11", string="2+", cat="pathology", note="Рекомендовано ISH"),
  obs("P-0063", "er-63", "Рецепторы эстрогена (ИГХ)", "2026-11-11", string="0%", cat="pathology"),
  # креатинина нет: анализы ещё не сданы
  board("P-0063", "enc-63", "2026-11-27"),
 ],
 "P-0077": [
  {"resourceType": "Patient", "id": "P-0077", "gender": "male", "birthDate": "2009-05-02",
   "name": [{"text": "Кузнецов И. А. (вымышленный)"}]},
  cond("P-0077", "c-77", "C81.1", "Лимфома Ходжкина, нодулярный склероз", "2026-11-10"),
  obs("P-0077", "crea-77", "Креатинин", "2026-11-10", "2160-0", 72, "umol/L"),
  board("P-0077", "enc-77", "2026-11-24"),
 ],
 "P-0024": [
  {"resourceType": "Patient", "id": "P-0024", "gender": "female", "birthDate": "1959-04-13",
   "name": [{"text": "Соколова А. Б. (вымышленная)"}]},
  cond("P-0024", "c-24", "C50.4", "Рак правой молочной железы, верхненаружный квадрант", "2026-11-09"),
  obs("P-0024", "her2-24", "HER2 (ИГХ)", "2026-11-09", string="0", cat="pathology"),
  obs("P-0024", "crea-24", "Креатинин", "2026-11-13", "2160-0", 64, "umol/L"),
  board("P-0024", "enc-24", "2026-11-20"),
 ],
}

DOCS = {
 "egd-301": "ЭГДС С БИОПСИЕЙ, 04.11.2026\n\nВ теле желудка по малой кривизне изъязвлённое образование до 35 мм с валикообразными краями. Взята биопсия (6 фрагментов).\nЗаключение: опухоль тела желудка, вероятно злокачественная.",
 "path-302": "ГИСТОЛОГИЧЕСКОЕ ИССЛЕДОВАНИЕ, 09.11.2026\n\nМатериал: биоптаты тела желудка.\nТубулярная аденокарцинома, умеренно дифференцированная (G2).\nИГХ HER2 — исследование в работе, результат будет дополнительно.",
 "ct-305": "КТ ГРУДНОЙ КЛЕТКИ И БРЮШНОЙ ПОЛОСТИ С КОНТРАСТИРОВАНИЕМ, 12.11.2026\n\nУтолщение стенки тела желудка до 14 мм на протяжении 40 мм. Перигастральные лимфоузлы до 9 мм.\nПечень, лёгкие — без очаговых изменений. Асцита нет.\nЗаключение: опухоль тела желудка; данных за отдалённые метастазы нет.",
}

for pid, rs in CASES.items():
    with open(f"data/{pid}.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(bundle(pid, rs), ensure_ascii=False, indent=1) + "\n")
for did, text in DOCS.items():
    with open(f"data/docs/{did}.md", "w", encoding="utf-8") as f:
        f.write("<!-- УЧЕБНЫЙ ВЫМЫШЛЕННЫЙ ДОКУМЕНТ -->\n" + text + "\n")
print(", ".join(f"{p}: {len(r)}" for p, r in CASES.items()))
