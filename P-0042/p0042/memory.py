"""Память агента (лекция 5): ссылка, а не копия; пространство имён на случай;
правки инструкций — только через ревью."""
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

REFS = ("Condition/", "Observation/", "Encounter/", "DocumentReference/", "ImagingStudy/")


class Store:
    """Минимальное хранилище с интерфейсом LangGraph Store: put / get / search / delete_namespace.
    В эксплуатации — база данных, а не память процесса (лекция 5, слайд 15)."""

    def __init__(self):
        self._d = {}

    def put(self, ns, key, value):
        self._d[(tuple(ns), key)] = value

    def get(self, ns, key):
        v = self._d.get((tuple(ns), key))
        return None if v is None else SimpleNamespace(key=key, value=v)

    def search(self, ns, query=None):
        """Только внутри своего пространства имён; query — подстрока (в проде — поиск по смыслу)."""
        ns = tuple(ns)
        out = []
        for (n, k), v in self._d.items():
            if n != ns:
                continue
            if query and query.lower() not in (k + " " + v.get("note", "")).lower():
                continue
            out.append(SimpleNamespace(key=k, value=v))
        return out

    def delete_namespace(self, ns):
        """Удаление всего о случае одной операцией (лекция 5, слайд 22)."""
        ns = tuple(ns)
        for key in [k for k in self._d if k[0] == ns]:
            del self._d[key]


def remember(store, case_id, key, source, author, note=""):
    """В память — ссылка на запись МИС и кто её записал."""
    if not source.startswith(REFS):
        raise ValueError("в памяти — ссылка, а не пересказ")
    store.put(("case", case_id), key, {
        "source": source, "note": note[:200],
        "author": author, "date": date.today().isoformat()})


def recall(store, case_id, query=None):
    """Ищем только в пространстве своего случая."""
    return store.search(("case", case_id), query=query)


def propose_instruction(store, current, draft):
    """Агент предлагает правку инструкции, но не применяет её."""
    pid = f"p-{uuid4().hex[:8]}"
    store.put(("instructions", "proposals"), pid, {"old": current, "new": draft, "status": "on_review"})
    return pid


def active_instructions(store, default=""):
    """Агент читает только принятую версию. Переносит из proposals в active человек."""
    item = store.get(("instructions", "active"), "agent")
    return item.value["text"] if item else default
