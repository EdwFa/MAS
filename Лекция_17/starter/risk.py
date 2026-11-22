"""Перечень опасностей и оценка риска (лекция 17, слайды 3–5).

hazards.md — таблица в Markdown: | id | опасность | тяжесть | вероятность | меры | тесты |.
Сетка слайда 5 записана кодом: положение в ней считает функция, а не человек на глаз.
"""
import pathlib
import re

SEVERITY = ("незначительный", "серьёзный", "критический")   # тяжесть: определяет врач
PROBABILITY = ("редко", "иногда", "часто")                    # вероятность: по тестам и атакам

# Зоны сетки слайда 5: (тяжесть, вероятность) → что делать
ZONE = {
    ("незначительный", "редко"): "принять", ("незначительный", "иногда"): "принять",
    ("незначительный", "часто"): "снижать",
    ("серьёзный", "редко"): "принять", ("серьёзный", "иногда"): "снижать",
    ("серьёзный", "часто"): "недопустимо",
    ("критический", "редко"): "снижать", ("критический", "иногда"): "недопустимо",
    ("критический", "часто"): "недопустимо",
}


def zone(severity, probability):
    if severity not in SEVERITY or probability not in PROBABILITY:
        raise ValueError(f"тяжесть из {SEVERITY}, вероятность из {PROBABILITY}")
    return ZONE[(severity, probability)]


def load_hazards(path):
    """Строки таблицы hazards.md → список словарей. Шапку и разделитель пропускаем."""
    rows = []
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 6 or not re.fullmatch(r"Н\d+", cells[0]):
            continue
        hid, text, sev, prob, measures, tests = cells
        rows.append({"id": hid, "hazard": text, "severity": sev, "probability": prob,
                     "measures": [m.strip() for m in measures.split(";") if m.strip()],
                     "tests": [t.strip() for t in tests.split(";") if t.strip()]})
    return rows


def review(rows):
    """Замечания к перечню: что не пройдёт ревью."""
    problems = []
    for r in rows:
        try:
            z = zone(r["severity"], r["probability"])
        except ValueError as e:
            problems.append(f"{r['id']}: {e}")
            continue
        if z != "принять" and not r["measures"]:
            problems.append(f"{r['id']}: зона «{z}», а мер нет")
        if r["measures"] and not r["tests"]:
            problems.append(f"{r['id']}: мера без теста — не принимается")
    return problems
