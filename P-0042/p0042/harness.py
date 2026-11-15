"""Мини-harness агента пакета (лекция 13): цикл «модель → инструмент → наблюдение»
с лимитом шагов, трассой и проверкой источников на выходе (лекция 7).

Протокол ответа модели — один JSON-объект:
  {"tool": "<имя>", "args": {...}}                   — вызвать инструмент
  {"final": {"answer": "...", "sources": [...], "open_questions": [...]}}  — закончить
"""
import json

from .memory import active_instructions

SYSTEM = """Ты готовишь справку к онкологическому консилиуму по случаю {case_id}.
Факты пациента бери только из карты через инструменты, знания — только из search_guidelines.
Каждое утверждение — со ссылкой на источник: запись карты (Type/id) или пункт рекомендаций (id).
Если нужного нет — так и скажи. Запись в карту только через chart_write.
Отвечай ровно одним JSON-объектом: {{"tool": ..., "args": {{...}}}} или {{"final": {{"answer": ..., "sources": [...]}}}}.
{extra}
Инструменты:
{tools}"""


def parse_action(reply):
    """Первый JSON-объект в ответе модели. Малые модели оборачивают его в ```json``` или текст."""
    try:
        return json.loads(reply)
    except ValueError:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(reply):
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(reply[i:])
                if isinstance(obj, dict) and ("tool" in obj or "final" in obj):
                    return obj
            except ValueError:
                continue
    raise ValueError("в ответе нет JSON-объекта с tool или final")


def refs_in(obj):
    """Все ссылки на источники, которые агент реально видел в наблюдениях."""
    out = set()
    if isinstance(obj, dict):
        if "resourceType" in obj and "id" in obj:
            out.add(f"{obj['resourceType']}/{obj['id']}")
        for k in ("ref", "id"):
            if isinstance(obj.get(k), str) and ("/" in obj[k] or "#" in obj[k]):
                out.add(obj[k])
        for v in obj.values():
            out |= refs_in(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= refs_in(v)
    return out


def run(question, case_id, llm, dispatch, trace, store=None, max_steps=8, release=None):
    extra = active_instructions(store) if store is not None else ""
    messages = [{"role": "system", "content": SYSTEM.format(
                    case_id=case_id, extra=extra,
                    tools=json.dumps(dispatch.tb.specs(), ensure_ascii=False))},
                {"role": "user", "content": question}]
    seen = set()
    trace.event("start", case_id=case_id, question=question,
                **({"release": release} if release else {}))
    for step in range(1, max_steps + 1):
        reply = llm(messages)
        messages.append({"role": "assistant", "content": reply})
        try:
            action = parse_action(reply)
        except ValueError:
            obs = {"isError": True, "text": "ответ не JSON: верни один JSON-объект по протоколу"}
        else:
            if "final" in action:
                return finish(action["final"], seen, step, trace)
            obs = dispatch(action.get("tool", ""), action.get("args", {}))
            seen |= refs_in(obs)
            if obs.get("status") == "waiting_doctor":
                trace.event("pause", step=step, reason="waiting_doctor")
                return {"status": "waiting_doctor", "steps": step, "answer": None, "sources": []}
        trace.event("step", step=step, observation=obs)
        messages.append({"role": "user", "content": "Наблюдение: " + json.dumps(obs, ensure_ascii=False, default=str)})
    trace.event("stop", reason="step_limit")
    return {"status": "step_limit", "steps": max_steps, "answer": None, "sources": []}


def finish(final, seen, step, trace):
    sources = list(final.get("sources", []))
    unsupported = [s for s in sources if s not in seen]
    status = "complete" if sources and not unsupported else "needs_review"
    trace.event("final", step=step, status=status, unsupported=unsupported)
    return {"status": status, "steps": step, "answer": final.get("answer", ""),
            "sources": sources, "unsupported_sources": unsupported,
            "open_questions": list(final.get("open_questions", []))}
