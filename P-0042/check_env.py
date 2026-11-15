"""Практикум 0: проверка окружения перед курсом.

    python check_env.py            # проверить всё, включая локальную модель
    python check_env.py --no-model # без модели (только Python, пакеты, данные, тесты)

Модель — локальный сервер с OpenAI-совместимым API (Ollama, vLLM, llama.cpp),
адрес и имя — в P0042_BASE_URL и P0042_MODEL. Данные пациента не уходят наружу.
"""
import importlib
import subprocess
import sys
import time

from p0042 import DATA

OK, FAIL = "✓", "✗"


def check(name, fn):
    try:
        detail = fn()
        print(f"{OK} {name}" + (f": {detail}" if detail else ""))
        return True
    except Exception as e:                        # noqa: BLE001 — показываем любую причину
        print(f"{FAIL} {name}: {e}")
        return False


def python_version():
    if sys.version_info < (3, 10):
        raise RuntimeError(f"нужен Python 3.10+, сейчас {sys.version.split()[0]}")
    return sys.version.split()[0]


def packages():
    from importlib.metadata import version
    for m in ("fastmcp", "jsonschema", "yaml"):
        importlib.import_module(m)
    return ", ".join(f"{p} {version(p)}" for p in ("fastmcp", "jsonschema", "pyyaml"))


def data():
    n = len(list(DATA.glob("P-*.json")))
    docs = len(list((DATA / "docs").glob("*.md")))
    if n < 5 or docs < 10:
        raise RuntimeError(f"данных мало: пациентов {n}, документов {docs}")
    return f"пациентов {n}, документов {docs}"


def tests():
    r = subprocess.run([sys.executable, "-m", "pytest", "-q"], capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or ["нет вывода"])[-1]
    if r.returncode:
        raise RuntimeError(last)
    return last


def model():
    from p0042.llm import LocalLLM
    llm = LocalLLM(timeout=120)
    t0 = time.perf_counter()
    out = llm("Ответь одним словом: столица России?")
    dt = time.perf_counter() - t0
    t0 = time.perf_counter()
    long = llm("Перечисли через запятую 30 любых медицинских терминов.")
    dt2 = time.perf_counter() - t0
    rate = len(long.split()) / dt2 if dt2 else 0
    return f"{llm.model} @ {llm.base_url}; первый ответ «{out.strip()[:30]}» за {dt:.1f} с; ≈{rate:.0f} слов/с"


if __name__ == "__main__":
    steps = [("Python", python_version), ("пакеты", packages), ("данные P-0042", data), ("тесты", tests)]
    if "--no-model" not in sys.argv:
        steps.append(("локальная модель", model))
    results = [check(n, f) for n, f in steps]
    sys.exit(0 if all(results) else 1)
