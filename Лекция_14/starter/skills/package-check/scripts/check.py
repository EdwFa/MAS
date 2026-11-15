"""Проверка обязательных полей пакета к консилиуму (лекция 14, слайд 14)."""
import json
import sys

REQUIRED = ["case_id", "diagnosis_ref", "imaging_ref",
            "histology_ref", "board_date", "open_questions"]


def check(pkg):
    # пустой список open_questions и «не назначена» — допустимы; нет ключа или пустая строка — нет
    problems = [f"нет поля {f}" for f in REQUIRED
                if pkg.get(f) in (None, "")]
    for f in ("diagnosis_ref", "imaging_ref", "histology_ref"):
        ref = pkg.get(f, "")
        if ref and "/" not in ref:
            problems.append(f"{f}: не ссылка FHIR вида Тип/id")
    board = pkg.get("board_date")
    if isinstance(board, list) and len(board) > 1:      # дополнение к слайду: спор дат
        problems.append("две даты консилиума: не выбирать, вынести спор в open_questions")
    return problems


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as fh:
        problems = check(json.load(fh))
    print(json.dumps({"ok": not problems, "problems": problems},
                     ensure_ascii=False))
    sys.exit(1 if problems else 0)
