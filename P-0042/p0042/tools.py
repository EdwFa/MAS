"""Инструменты и диспетчер (лекции 4, 9, 16).

Порядок проверки любого вызова: имя → схема → лимит → политика → вызов.
Любой отказ и любая ошибка возвращаются модели как наблюдение, а не как исключение.
"""
import hashlib

from jsonschema import ValidationError, validate

from .calc import CalcError, egfr


def tool(name, description, schema, policy="allow", limit=5):
    def wrap(fn):
        fn.spec = {"name": name, "description": description, "inputSchema": schema,
                   "policy": policy, "limit": limit}
        return fn
    return wrap


class Toolbox:
    """Инструменты агента пакета. fhir, rag и chart — внедряемые зависимости."""

    def __init__(self, fhir, rag=None, chart=None):
        self.fhir, self.rag = fhir, rag
        self.chart = chart if chart is not None else []      # «карта» для записей
        self.ledger = set()                                   # лекция 16: без дублей
        self.registry = {f.spec["name"]: f for f in (
            self.fhir_read, self.latest_lab, self.calc_egfr, self.search_guidelines, self.chart_write)}

    def specs(self):
        """То, что видит модель: имя, описание, схема. Политику и лимит модель не видит."""
        return [{k: f.spec[k] for k in ("name", "description", "inputSchema")}
                for f in self.registry.values()]

    @tool("fhir_read", "Прочитать запись карты по ссылке вида Type/id.",
          {"type": "object", "required": ["ref"], "additionalProperties": False,
           "properties": {"ref": {"type": "string", "pattern": "^[A-Za-z]+/[A-Za-z0-9-]+$"}}})
    def fhir_read(self, ref):
        rtype, rid = ref.split("/")
        return self.fhir.read(rtype, rid)

    @tool("latest_lab", "Последний результат теста пациента: значение, дата и ссылка на запись.",
          {"type": "object", "required": ["case_id", "test"], "additionalProperties": False,
           "properties": {"case_id": {"type": "string"}, "test": {"type": "string"}}})
    def latest_lab(self, case_id, test):
        r = self.fhir.latest(case_id, test)
        if r is None:
            return {"found": False}
        q = r["valueQuantity"]
        return {"found": True, "value": q["value"], "unit": q["unit"],
                "date": r["effectiveDateTime"], "ref": self.fhir.ref(r)}

    @tool("egfr", "Расчётная СКФ по CKD-EPI 2021 и категория KDIGO. Только взрослые. Расчёт, а не диагноз.",
          {"type": "object", "required": ["sex", "age", "creatinine"], "additionalProperties": False,
           "properties": {"sex": {"enum": ["female", "male"]}, "age": {"type": "integer"},
                          "creatinine": {"type": "number"}, "unit": {"enum": ["umol/L", "mg/dL"]}}},
          limit=2)
    def calc_egfr(self, **args):
        return egfr(**args)

    @tool("search_guidelines", "Поиск по действующим учебным рекомендациям. Возвращает пункты с УУР/УДД.",
          {"type": "object", "required": ["query"], "additionalProperties": False,
           "properties": {"query": {"type": "string", "maxLength": 200}}},
          limit=4)
    def search_guidelines(self, query):
        if self.rag is None:
            raise RuntimeError("индекс рекомендаций не подключён")
        return [{"id": c["id"], "section": c["section"], "text": c["text"]} for c in self.rag.answer_context(query)]

    @tool("chart_write", "Записать заключение в карту. Требует подтверждения врача.",
          {"type": "object", "required": ["case_id", "text"], "additionalProperties": False,
           "properties": {"case_id": {"type": "string"}, "text": {"type": "string", "maxLength": 2000}}},
          policy="ask", limit=1)
    def chart_write(self, case_id, text):
        key = hashlib.sha256(f"{case_id}|{text}".encode()).hexdigest()[:16]
        if key in self.ledger:                     # повтор — не дубль
            return {"status": "already_written", "key": key}
        self.ledger.add(key)
        self.chart.append({"case_id": case_id, "text": text, "key": key})
        return {"status": "written", "key": key}


class Dispatcher:
    """Между моделью и инструментами. confirm(name, args) -> True | False | None (врач ещё не ответил)."""

    def __init__(self, toolbox, confirm=None, trace=None):
        self.tb, self.confirm, self.trace = toolbox, confirm, trace
        self.used = {}

    def __call__(self, name, args):
        out = self._dispatch(name, args or {})
        if self.trace is not None:
            self.trace.event("tool", name=name, args=args, result=out)
        return out

    def _dispatch(self, name, args):
        fn = self.tb.registry.get(name)
        if fn is None:                                           # белый список
            return {"isError": True, "text": f"нет инструмента {name}"}
        try:
            validate(args, fn.spec["inputSchema"])
        except ValidationError as e:
            return {"isError": True, "text": f"аргументы {name}: {e.message}"}
        self.used[name] = self.used.get(name, 0) + 1
        if self.used[name] > fn.spec["limit"]:                   # лекция 9
            return {"isError": True, "text": f"лимит {name} исчерпан: ответь по найденному или скажи «не найдено»"}
        if fn.spec["policy"] == "ask":                           # лекция 4
            answer = self.confirm(name, args) if self.confirm else None
            if answer is None:
                self.used[name] -= 1
                return {"status": "waiting_doctor", "text": "ждём подтверждения врача; это не ошибка"}
            if answer is False:
                return {"status": "declined", "text": "врач отказал в записи"}
        try:
            out = fn(**args)
            return out if isinstance(out, dict) else {"result": out}
        except (KeyError, CalcError, RuntimeError) as e:
            return {"isError": True, "text": str(e).strip("'\"")}
