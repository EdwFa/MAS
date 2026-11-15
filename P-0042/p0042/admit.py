"""Хост пускает к модели только одобренные и не изменённые после ревью инструменты (лекция 6)."""
import hashlib
import json


def fingerprint(tool):
    """Отпечаток того, что читает модель."""
    seen = {k: tool.get(k) for k in ("name", "description", "inputSchema")}
    raw = json.dumps(seen, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def admit(server, tools, approved, alert):
    ok = []
    for t in tools:
        key = f"{server}/{t['name']}"
        if approved.get(key) != fingerprint(t):
            alert(key, "новый или изменённый инструмент")
            continue
        ok.append(t)
    return ok
