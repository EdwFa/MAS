"""Трасса: каждое событие — строка JSON (лекции 13 и 17).
Поля совместимы по смыслу с OpenTelemetry GenAI: шаг, инструмент, аргументы, результат."""
import json
import time
from uuid import uuid4


class Trace:
    def __init__(self, path=None, run_id=None):
        self.run_id = run_id or uuid4().hex[:12]
        self.path = path
        self.events = []

    def event(self, kind, **data):
        e = {"run_id": self.run_id, "t": round(time.time(), 3), "kind": kind, **data}
        self.events.append(e)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
        return e

    def of(self, kind):
        return [e for e in self.events if e["kind"] == kind]
