"""Учебное хранилище FHIR: чтение синтетических пакетов из data/*.json (только чтение)."""
import json

from . import DATA


class FHIRStore:
    def __init__(self, folder=DATA):
        self.res = {}
        for path in sorted(folder.glob("P-*.json")):
            bundle = json.loads(path.read_text(encoding="utf-8"))
            for entry in bundle["entry"]:
                r = entry["resource"]
                self.res[(r["resourceType"], r["id"])] = r

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
            subj = r.get("subject", {}).get("reference") or (f"Patient/{r['id']}" if t == "Patient" else "")
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

    @staticmethod
    def ref(r):
        return f"{r['resourceType']}/{r['id']}"
