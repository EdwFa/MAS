"""Учебное хранилище FHIR: чтение синтетических данных из data/ (только чтение).

База (P-*.json) — состояние карты на утро понедельника 16.11.2026.
as_of="2026-11-18" добавляет события хронологии timeline_*.jsonl до этой даты
включительно: новые записи и изменения статусов (лекции 5 и 16).
"""
import copy
import json
import re

from . import DATA

COMMENT = re.compile(r"<!--.*?-->\s*", re.S)


class FHIRStore:
    def __init__(self, folder=DATA, as_of=None):
        self.folder = folder
        self.res = {}
        self.timeline = []
        for path in sorted(folder.glob("P-*.json")):
            bundle = json.loads(path.read_text(encoding="utf-8"))
            for entry in bundle["entry"]:
                r = entry["resource"]
                self.res[(r["resourceType"], r["id"])] = r
        for path in sorted(folder.glob("timeline_*.jsonl")):
            self.timeline += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        self.as_of = None
        if as_of:
            self.advance(as_of)

    def advance(self, as_of):
        """Применить события хронологии до даты включительно (повторно не применяются)."""
        start = self.as_of or ""
        for e in self.timeline:
            if not (start < e["date"] <= as_of):
                continue
            if e["kind"] == "resource":
                r = copy.deepcopy(e["resource"])
                self.res[(r["resourceType"], r["id"])] = r
            elif e["kind"] == "update":
                rtype, rid = e["ref"].split("/")
                self.res[(rtype, rid)].update(e["set"])
        self.as_of = as_of

    def events(self, kind=None, as_of=None):
        """События хронологии (запросы врача, уведомления A2A) до даты включительно."""
        until = as_of or self.as_of or ""
        return [e for e in self.timeline if e["date"] <= until and (kind is None or e["kind"] == kind)]

    def read(self, rtype, rid):
        """Одна запись по типу и id. Нет записи — KeyError с понятным текстом."""
        try:
            return self.res[(rtype, rid)]
        except KeyError:
            raise KeyError(f"нет записи {rtype}/{rid}") from None

    def search(self, rtype, patient_id, text=None):
        """Записи пациента данного типа; text — подстрока в code.text (без регистра)."""
        out = []
        for (t, _), r in self.res.items():
            if t != rtype:
                continue
            subj = (r.get("subject") or r.get("patient") or {}).get("reference") \
                or (f"Patient/{r['id']}" if t == "Patient" else "")
            if subj != f"Patient/{patient_id}":
                continue
            if text and text.lower() not in r.get("code", {}).get("text", "").lower():
                continue
            out.append(r)
        return out

    def latest(self, patient_id, text):
        """Последнее наблюдение пациента по названию теста (лекция 9: «факт из карты»)."""
        obs = self.search("Observation", patient_id, text)
        if not obs:
            return None
        return max(obs, key=lambda r: r.get("effectiveDateTime", ""))

    def document_text(self, rid):
        """Текст документа без служебной пометки. Это данные, а не инструкции (лекция 17)."""
        r = self.read("DocumentReference", rid)
        path = self.folder / r["content"][0]["attachment"]["url"]
        return COMMENT.sub("", path.read_text(encoding="utf-8")).strip()

    @staticmethod
    def ref(r):
        return f"{r['resourceType']}/{r['id']}"
