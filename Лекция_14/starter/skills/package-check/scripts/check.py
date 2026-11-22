"""Проверка обязательных полей пакета к консилиуму (лекция 14, слайд 14).

Только стандартная библиотека Python 3. Вызов: python check.py work/package.json
Выход — одна строка JSON в stdout. Коды возврата:
  0 — пакет в порядке, 1 — есть problems, 2 — пакет не прочитан (error).
"""
import json
import sys

# Поля, без которых консилиум не начинают (references/fields.md).
REQUIRED = ["case_id", "diagnosis_ref", "imaging_ref",
            "histology_ref", "board_date", "open_questions"]
FHIR_REFS = ("diagnosis_ref", "imaging_ref", "histology_ref")   # ссылка вида Тип/id


def check(pkg):
    # пустой список open_questions и «не назначена» — допустимы; нет ключа или пустая строка — нет
    problems = [f"нет поля {f}" for f in REQUIRED
                if pkg.get(f) in (None, "")]
    for f in FHIR_REFS:
        ref = pkg.get(f, "")
        if ref and "/" not in ref:
            problems.append(f"{f}: не ссылка FHIR вида Тип/id")
    board = pkg.get("board_date")
    if isinstance(board, list) and len(board) > 1:      # дополнение к слайду: спор дат
        problems.append("две даты консилиума: не выбирать, вынести спор в open_questions")
    return problems


def fail(msg):
    """Ошибку решаем здесь, а не перекладываем на модель: понятный JSON и код 2."""
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    sys.exit(2)


def main(argv):
    if len(argv) != 2:
        fail("ожидался один аргумент: путь к пакету, например work/package.json")
    try:
        with open(argv[1], encoding="utf-8") as fh:
            pkg = json.load(fh)
    except FileNotFoundError:
        fail(f"файл {argv[1]} не найден: попроси harness положить пакет случая")
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        fail(f"файл {argv[1]} не JSON в UTF-8: {e}")
    if not isinstance(pkg, dict):
        fail("пакет должен быть JSON-объектом с полями из references/fields.md")
    problems = check(pkg)
    print(json.dumps({"ok": not problems, "problems": problems},
                     ensure_ascii=False))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main(sys.argv)
