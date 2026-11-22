"""Матрица прослеживаемости (лекция 17, слайд 25): каждая строка ссылается на существующий тест."""
import csv
import pathlib
import re

COLUMNS = ["requirement", "hazard", "measure", "test", "result", "residual_risk"]


def check(path, root):
    problems = []
    with open(path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != COLUMNS:
            return [f"столбцы должны быть: {', '.join(COLUMNS)}"]
        for i, row in enumerate(reader, 2):
            if any(not row[c].strip() for c in COLUMNS):
                problems.append(f"строка {i}: пустая ячейка")
                continue
            if not re.fullmatch(r"Н\d+", row["hazard"].strip()):
                problems.append(f"строка {i}: опасность — код из перечня (Н1…)")
            m = re.fullmatch(r"(.+\.py)::(test_\w+)", row["test"].strip())
            if not m:
                problems.append(f"строка {i}: тест в виде файл.py::test_имя")
                continue
            f = pathlib.Path(root) / m.group(1)
            if not f.is_file() or f"def {m.group(2)}(" not in f.read_text(encoding="utf-8"):
                problems.append(f"строка {i}: тест {row['test']} не найден — строка не принимается")
    return problems
