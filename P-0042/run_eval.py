"""Прогон агента на наборах eval/ с локальной моделью (лекции 8, 9, 17, 18).

    python run_eval.py > eval_result.json

Итог совместим с ops.gate: сохраните результат прежнего релиза и сравните.
"""
import json

from p0042.evaluate import retrieval_recall, run_suite
from p0042.fhir import FHIRStore
from p0042.harness import run
from p0042.llm import LocalLLM
from p0042.ops import load_release
from p0042.rag import Index
from p0042.tools import Dispatcher, Toolbox
from p0042.trace import Trace


def make_agent(rel, index):
    llm = LocalLLM(model=rel["model"]["name"])

    def agent(question, case_id, as_of):
        tb = Toolbox(FHIRStore(as_of=as_of), index)
        trace = Trace("trace.jsonl")
        res = run(question, case_id, llm, Dispatcher(tb, confirm=None, trace=trace), trace,
                  max_steps=rel["limits"]["max_steps"], release=rel["release"])
        res["written"] = bool(tb.chart)          # без подтверждения врача записей быть не должно
        return res
    return agent


def main():
    rel, index = load_release(), Index()
    result = run_suite(make_agent(rel, index), tools=Toolbox(FHIRStore(), index).specs())
    result["retrieval_recall@20"] = retrieval_recall(index)[0]
    result["release"] = f'{rel["release"]}+{rel["fingerprint"]}'
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
