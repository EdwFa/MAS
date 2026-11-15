"""Запуск агента пакета на локальной модели.

    python run.py "Какая СКФ у пациентки и что рекомендации говорят о дозах?"

Переменные: P0042_BASE_URL (по умолчанию http://localhost:11434/v1), P0042_MODEL.
Трасса пишется в trace.jsonl.
"""
import json
import sys

from p0042.fhir import FHIRStore
from p0042.harness import run
from p0042.llm import LocalLLM
from p0042.memory import Store
from p0042.rag import Index
from p0042.tools import Dispatcher, Toolbox
from p0042.trace import Trace


def ask_doctor(name, args):
    reply = input(f"\nАгент просит {name}: {json.dumps(args, ensure_ascii=False)}\nРазрешить? [y/n/пусто — позже] ")
    return {"y": True, "n": False}.get(reply.strip().lower())


def main():
    question = " ".join(sys.argv[1:]) or "Посчитай СКФ по последнему креатинину и найди, что рекомендации говорят о сниженной функции почек."
    trace = Trace("trace.jsonl")
    dispatch = Dispatcher(Toolbox(FHIRStore(), Index()), confirm=ask_doctor, trace=trace)
    result = run(question, "P-0042", LocalLLM(), dispatch, trace, store=Store())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
