"""Генерирует data/P-0042.json и data/timeline_P-0042.jsonl — синтетический случай.
Запуск из папки P-0042:  python tools/make_p0042.py
Все данные вымышленные. Клиническую правдоподобность проверяет преподаватель."""
import json

P = {"reference": "Patient/P-0042"}

def obs(id, text, date, loinc=None, qty=None, unit=None, string=None, integer=None, note=None, cat="laboratory"):
    r = {"resourceType": "Observation", "id": id, "status": "final", "subject": P,
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

def doc(id, date, desc, kind, author=None):
    r = {"resourceType": "DocumentReference", "id": id, "status": "current", "subject": P,
         "date": date, "type": {"text": kind}, "description": desc,
         "content": [{"attachment": {"contentType": "text/markdown", "url": f"docs/{id}.md"}}]}
    if author:
        r["author"] = [{"reference": author}]
    return r

R = [
 {"resourceType": "Patient", "id": "P-0042", "gender": "female", "birthDate": "1959-03-14",
  "name": [{"text": "Соколова А. В. (вымышленная)"}]},
 {"resourceType": "Practitioner", "id": "dr-17", "name": [{"text": "Онколог-химиотерапевт (вымышленный)"}]},
 {"resourceType": "Practitioner", "id": "dr-21", "name": [{"text": "Кардиолог (вымышленный)"}]},
 {"resourceType": "Practitioner", "id": "dr-05", "name": [{"text": "Онколог-хирург (вымышленный)"}]},
 # диагнозы: устаревшая предварительная запись и уточнённый диагноз
 {"resourceType": "Condition", "id": "c-09", "subject": P, "recordedDate": "2026-11-05",
  "verificationStatus": "provisional", "code": {"text": "Образование левой молочной железы, под вопросом"},
  "note": [{"text": "До гистологии. Заменено записью c-17"}]},
 {"resourceType": "Condition", "id": "c-17", "subject": P, "recordedDate": "2026-11-12",
  "verificationStatus": "confirmed",
  "code": {"coding": [{"system": "ICD-10", "code": "C50.4"}],
           "text": "Рак левой молочной железы, верхненаружный квадрант"},
  "note": [{"text": "Диагноз уточнён по гистологии 12.11"}]},
 {"resourceType": "Condition", "id": "c-03", "subject": P, "recordedDate": "2014-05-20",
  "verificationStatus": "confirmed", "code": {"coding": [{"system": "ICD-10", "code": "E11.9"}], "text": "Сахарный диабет 2 типа"}},
 {"resourceType": "Condition", "id": "c-04", "subject": P, "recordedDate": "2011-09-02",
  "verificationStatus": "confirmed", "code": {"coding": [{"system": "ICD-10", "code": "I10"}], "text": "Артериальная гипертензия"}},
 # хроническая болезнь почек в списке диагнозов НЕ записана — пробел, который агент должен показать
 {"resourceType": "FamilyMemberHistory", "id": "fmh-1", "patient": P, "status": "completed", "date": "2026-11-06",
  "relationship": {"text": "мать"},
  "condition": [{"code": {"text": "Рак яичников"}, "onsetAge": {"value": 58, "unit": "лет"}}]},
 {"resourceType": "AllergyIntolerance", "id": "al-1", "patient": P, "recordedDate": "2019-04-11",
  "code": {"text": "Йодсодержащие рентгеноконтрастные средства"},
  "reaction": [{"description": "Крапивница после КТ с контрастом (2019)"}]},
 {"resourceType": "MedicationStatement", "id": "med-1", "subject": P, "status": "active",
  "medication": {"concept": {"text": "Метформин 1000 мг"}}, "dosage": [{"text": "по 1 таблетке 2 раза в день"}]},
 {"resourceType": "MedicationStatement", "id": "med-2", "subject": P, "status": "active",
  "medication": {"concept": {"text": "Лизиноприл 10 мг"}}, "dosage": [{"text": "1 раз в день"}]},
 {"resourceType": "MedicationStatement", "id": "med-3", "subject": P, "status": "active",
  "medication": {"concept": {"text": "Аторвастатин 20 мг"}}, "dosage": [{"text": "1 раз в день вечером"}]},
 # опухоль
 obs("her2-77", "HER2 (ИГХ)", "2026-11-10", string="3+", cat="pathology"),
 obs("er-77", "Рецепторы эстрогена (ИГХ)", "2026-11-10", string="0%", cat="pathology"),
 obs("pr-77", "Рецепторы прогестерона (ИГХ)", "2026-11-10", string="0%", cat="pathology"),
 # Ki-67 не выполнен — открытый вопрос к консилиуму (лекции 13, 15)
 obs("grade-77", "Степень злокачественности", "2026-11-10", string="G2", cat="pathology"),
 # почки и анализы
 obs("crea-201", "Креатинин", "2026-11-03", "2160-0", 118, "umol/L"),
 obs("crea-233", "Креатинин", "2026-11-13", "2160-0", 124, "umol/L"),
 obs("crea-233b", "Креатинин", "2026-11-13", "2160-0", 124, "umol/L",
     note="Дубль: та же проба, повторно пришла из ЛИС при интеграции"),
 obs("k-233", "Калий", "2026-11-13", "2823-3", 4.9, "mmol/L"),
 obs("hba1c-190", "Гликированный гемоглобин HbA1c", "2026-11-03", "4548-4", 7.4, "%"),
 obs("hb-233", "Гемоглобин", "2026-11-13", "718-7", 128, "g/L"),
 obs("wbc-233", "Лейкоциты", "2026-11-13", "6690-2", 6.1, "10^9/L"),
 obs("plt-233", "Тромбоциты", "2026-11-13", "777-3", 245, "10^9/L"),
 obs("alt-233", "АЛТ", "2026-11-13", "1742-6", 22, "U/L"),
 obs("ast-233", "АСТ", "2026-11-13", "1920-8", 25, "U/L"),
 obs("bili-233", "Билирубин общий", "2026-11-13", "1975-2", 12, "umol/L"),
 # антропометрия, статус, сердце
 obs("height-1", "Рост", "2026-11-03", "8302-2", 162, "cm", cat="vital-signs"),
 obs("weight-1", "Масса тела", "2026-11-03", "29463-7", 74, "kg", cat="vital-signs"),
 obs("ecog-1", "Статус ECOG", "2026-11-06", integer=1, cat="survey"),
 obs("lvef-215", "Фракция выброса левого желудочка (ЭхоКГ)", "2026-11-14", "10230-1", 58, "%", cat="imaging"),
 # визиты и консилиум
 {"resourceType": "Encounter", "id": "enc-12", "subject": P, "status": "finished",
  "type": [{"text": "Консультация онколога-хирурга"}], "period": {"start": "2026-11-06"},
  "participant": [{"actor": {"reference": "Practitioner/dr-05"}}]},
 {"resourceType": "Encounter", "id": "enc-15", "subject": P, "status": "finished",
  "type": [{"text": "Консультация кардиолога"}], "period": {"start": "2026-11-14"},
  "participant": [{"actor": {"reference": "Practitioner/dr-21"}}]},
 {"resourceType": "Encounter", "id": "enc-31", "subject": P, "status": "planned",
  "type": [{"text": "Онкологический консилиум"}], "period": {"start": "2026-11-20"}},
 # внешний анализ: заказан, результат придёт позже (см. timeline_P-0042.jsonl)
 {"resourceType": "ServiceRequest", "id": "sr-brca-7", "subject": P, "status": "active", "intent": "order",
  "authoredOn": "2026-11-12", "code": {"text": "Герминальные варианты BRCA1/BRCA2"},
  "performer": [{"display": "Лаборатория молекулярной генетики «Геном-Тест» (вымышленная)"}]},
 # документы со свободным текстом
 doc("ext-090", "2026-10-28", "Выписка из другого стационара", "Выписной эпикриз"),
 doc("mmg-180", "2026-11-04", "Маммография", "Протокол исследования"),
 doc("us-188", "2026-11-05", "УЗИ молочных желёз и регионарных лимфоузлов", "Протокол исследования"),
 doc("path-201", "2026-11-10", "Гистологическое и ИГХ-исследование биопсии", "Протокол исследования"),
 doc("ct-117", "2026-11-11", "Направление на КТ. В тексте: «консилиум 27.11»", "Направление", "Practitioner/dr-05"),
 doc("cardio-215", "2026-11-14", "Консультация кардиолога", "Консультация", "Practitioner/dr-21"),
 doc("ct-219", "2026-11-14", "КТ грудной клетки и брюшной полости без контрастирования", "Протокол исследования"),
 doc("bone-220", "2026-11-16", "Сцинтиграфия костей скелета", "Протокол исследования"),
]

bundle = {"resourceType": "Bundle", "type": "collection",
          "meta": {"tag": [{"code": "synthetic", "display": "Учебные вымышленные данные. Не реальный пациент."}]},
          "entry": [{"resource": r} for r in R]}
open("data/P-0042.json", "w", encoding="utf-8").write(json.dumps(bundle, ensure_ascii=False, indent=1) + "\n")
print(len(R), "resources")

# Хронология: что появляется по дням. База (bundle) — состояние на утро понедельника 16.11.
brca = {"resourceType": "DiagnosticReport", "id": "brca-7", "status": "final", "subject": P,
        "basedOn": [{"reference": "ServiceRequest/sr-brca-7"}], "issued": "2026-11-18",
        "code": {"text": "Герминальные варианты BRCA1/BRCA2"},
        "conclusion": "Патогенных и вероятно патогенных вариантов не выявлено",
        "presentedForm": [{"contentType": "text/markdown", "url": "docs/brca-7.md"}]}
T = [
 {"date": "2026-11-16", "day": "пн", "kind": "request", "from": "Practitioner/dr-17",
  "text": "Начните собирать пакет P-0042 к консилиуму. Ссылки на источники — в начале, СКФ отдельной строкой."},
 {"date": "2026-11-17", "day": "вт", "kind": "resource",
  "resource": obs("tnm-1", "Клиническая стадия", "2026-11-17", string="cT2N1M0, IIB",
                  note="Предварительно, по УЗИ, КТ и сцинтиграфии. Подтверждает консилиум", cat="staging")},
 {"date": "2026-11-18", "day": "ср", "kind": "a2a_notification", "message_id": "m-551", "task_id": "brca-7",
  "state": "completed", "artifact": "DiagnosticReport/brca-7"},
 {"date": "2026-11-18", "day": "ср", "kind": "a2a_notification", "message_id": "m-551", "task_id": "brca-7",
  "state": "completed", "artifact": "DiagnosticReport/brca-7",
  "note": "Повтор того же уведомления (доставка «хотя бы один раз», лекция 16)"},
 {"date": "2026-11-18", "day": "ср", "kind": "resource", "resource": brca},
 {"date": "2026-11-18", "day": "ср", "kind": "update", "ref": "ServiceRequest/sr-brca-7", "set": {"status": "completed"}},
 {"date": "2026-11-19", "day": "чт", "kind": "request", "from": "Practitioner/dr-17",
  "text": "Пакет нужен сегодня к 16:00. Дату консилиума уточните: в направлении на КТ стоит 27.11."},
 {"date": "2026-11-20", "day": "пт", "kind": "event", "ref": "Encounter/enc-31", "text": "Консилиум по плану в МИС"},
]
with open("data/timeline_P-0042.jsonl", "w", encoding="utf-8") as f:
    for e in T:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
print(len(T), "timeline events")
