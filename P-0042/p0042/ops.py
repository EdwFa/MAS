"""Эксплуатация (лекция 18): релиз, проверка релиза, тихий режим, дневные метрики."""
import hashlib
import json
from collections import Counter

import yaml

from . import ROOT
from .harness import SYSTEM


def load_release(path=ROOT / "release.yaml"):
    """Манифест релиза и отпечаток всего, что в нём закреплено (вместе с текстом промпта)."""
    rel = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw = json.dumps(rel, sort_keys=True, ensure_ascii=False) + SYSTEM
    rel["fingerprint"] = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return rel


def gate(candidate, baseline, run_eval):
    """Новый релиз выходит, только если он не хуже прежнего
    на наборе и не приносит новых критических ошибок."""
    new, old = run_eval(candidate), run_eval(baseline)
    checks = {
        "sources": new["supported"] >= old["supported"] - 0.01,
        "critical": not set(new["critical"]) - set(old["critical"]),
        "refusals": new["honest_refusal"] >= old["honest_refusal"],
        "attacks": new["attack_success"] <= old["attack_success"],
        "latency": new["p95_s"] <= old["p95_s"] * 1.2,
    }
    return all(checks.values()), checks


def silent_compare(agent_pkg, doctor_pkg):
    """Тихий режим: что агент нашёл, а врач нет, и наоборот."""
    a, d = set(agent_pkg["sources"]), set(doctor_pkg["sources"])
    return {"both": sorted(a & d),
            "agent_only": sorted(a - d),
            "doctor_only": sorted(d - a),
            "recall": len(a & d) / len(d) if d else None,
            "open_questions": agent_pkg.get("open_questions", [])}


def summarize(pairs):
    """Итог тихого режима за период."""
    reports = [silent_compare(a, d) for a, d in pairs]
    complete = [r for r in reports if not r["doctor_only"]]
    return {"cases": len(reports),
            "nothing_missed": len(complete) / max(len(reports), 1),
            "to_review": [r for r in reports if r["doctor_only"]]}


def feedback(trace, verdict, note=""):
    """Решение врача по пакету — одна строка в трассе."""
    if verdict not in ("accepted", "edited", "rejected"):
        raise ValueError("verdict: accepted | edited | rejected")
    return trace.event("feedback", verdict=verdict, note=note[:500])


def daily(events):
    """Сводка за день по событиям трассы harness."""
    finals = [e for e in events if e["kind"] == "final"]
    status = Counter(e["status"] for e in finals)
    fb = Counter(e["verdict"] for e in events if e["kind"] == "feedback")
    n, m = max(len(finals), 1), max(sum(fb.values()), 1)
    steps = sorted(e["step"] for e in finals) or [0]
    return {
        "runs": len(finals),
        "releases": sorted({e["release"] for e in events if e["kind"] == "start" and "release" in e}),
        "needs_review": status["needs_review"] / n,
        "accepted_as_is": fb["accepted"] / m,
        "edited": fb["edited"] / m,
        "rejected": fb["rejected"] / m,
        "steps_p95": steps[int(0.95 * (len(steps) - 1))],
    }
