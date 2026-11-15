"""Оркестрация RAG (лекция 9): маршрут по сложности, параллельные ветви,
оценка найденного, цикл с бюджетом."""
import asyncio
import json

from jsonschema import ValidationError, validate

from .rag import rrf

ROUTE = {"type": "object", "required": ["kind", "confidence"],
         "properties": {
             "kind": {"enum": ["chart_fact", "single", "multi"]},
             "confidence": {"type": "number", "minimum": 0, "maximum": 1}},
         "additionalProperties": False}
SAFER = {"chart_fact": "single", "single": "multi", "multi": "multi"}

CLASSIFY = ("Отнеси вопрос врача к одному виду: chart_fact (факт из карты), single (один пункт "
            "рекомендаций), multi (сложный вопрос). Ответь JSON {{\"kind\": ..., \"confidence\": 0..1}}.\n"
            "Вопрос: {question}")


def route_question(question, llm, threshold=0.8):
    """Путь по сложности; при сомнении — на ступень тщательнее."""
    try:
        out = json.loads(llm(CLASSIFY.format(question=question)))
        validate(out, ROUTE)
    except (ValueError, ValidationError):
        return "multi"
    if out["confidence"] < threshold:
        return SAFER[out["kind"]]
    return out["kind"]


async def search_all(subqueries, search, timeout=5.0):
    """Подзапросы ищем параллельно; медленная ветка не держит остальные."""
    missed = []

    async def one(q):
        try:
            return await asyncio.wait_for(search(q), timeout)
        except asyncio.TimeoutError:
            missed.append(q)
            return []

    rankings = await asyncio.gather(*(one(s["q"]) for s in subqueries))
    return rrf([r for r in rankings if r]), missed


def grade(question, chunks, judge, hi=0.7, lo=0.3):
    """Хватает ли найденного: correct, ambiguous, incorrect."""
    best = max((judge(question, c["text"]) for c in chunks), default=0.0)
    if best >= hi:
        return "correct"
    if best >= lo:
        return "ambiguous"
    return "incorrect"


def answer_loop(question, retrieve, rewrite, judge, write, max_steps=3):
    """Ищем, пока найденного не хватит или не кончится бюджет.
    write(question, context) -> текст ответа."""
    query, context, trace, seen = question, [], [], set()
    verdict = "incorrect"
    for step in range(1, max_steps + 1):
        found = retrieve(query)
        verdict = grade(question, found, judge)
        trace.append({"step": step, "query": query, "verdict": verdict, "found": len(found)})
        if verdict != "incorrect":
            context += [c for c in found if c not in context]
        if verdict == "correct":
            break
        seen.add(query)
        query = rewrite(question, query)
        if query in seen:
            break
    if not context:
        return {"answer": "в рекомендациях не найдено", "status": "not_found", "trace": trace}
    return {"answer": write(question, context), "status": verdict, "trace": trace, "context": context}
