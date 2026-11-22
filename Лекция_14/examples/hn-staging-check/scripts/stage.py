"""Группа стадии рака головы и шеи по T, N, M (учебный пример к лекции 14).

Вызов: python stage.py work/staging.json
Выход — одна строка JSON. Коды возврата:
  0 — рассчитанная стадия совпадает с записанной,
  1 — расхождение (или записанной стадии нет),
  2 — посчитать нельзя: не хватает или неверны входные данные (поле error).
Таблицы и источники — references/staging_tables.md. Только стандартная библиотека.
"""
import json
import re
import sys

SITES = {"oral_cavity", "larynx", "hypopharynx", "oropharynx", "nasopharynx"}
T_ORDER = ["T0", "Tis", "T1", "T2", "T3", "T4", "T4a", "T4b"]


def norm(value, axis):
    """pT2 → T2, N2b → N2, N3a → N3. Возвращает None, если категория непонятна."""
    v = re.sub(r"^(yp|c|p|r)", "", str(value).strip(), flags=re.I)
    v = v[0].upper() + v[1:] if v else v
    if axis == "T":
        return v if v in T_ORDER else None
    if axis == "N":
        m = re.fullmatch(r"N([0-3])[a-c]?", v)
        return f"N{m.group(1)}" if m else None
    if axis == "M":
        return v if v in ("M0", "M1", "M1a", "M1b") else None


def t_num(t):
    return {"T0": 0, "T1": 1, "T2": 2, "T3": 3, "T4": 4, "T4a": 4, "T4b": 4}[t]


def common(t, n, m):                                # раздел 1
    if m.startswith("M1"):
        return "IVC"
    if t == "Tis":
        return "0" if n == "N0" else None
    if t == "T0":
        return None                                 # T0 вне p16+ ротоглотки и носоглотки — вопрос врачу
    if t == "T4b" or n == "N3":
        return "IVB"
    if t == "T4":
        return None                                 # в общей таблице нужна подкатегория T4a/T4b
    if t == "T4a" and n in ("N0", "N1") or n == "N2":
        return "IVA"
    if n == "N1":
        return "III"
    return {"T1": "I", "T2": "II", "T3": "III"}[t]


def p16_clinical(t, n, m):                          # раздел 2
    if m.startswith("M1"):
        return "IV"
    if t == "Tis":
        return None
    k = t_num(t)
    if n == "N3" or k == 4:
        return "III"
    if k <= 2:
        return "I" if n in ("N0", "N1") else "II"
    return "II"                                     # T3, N0–N2


def p16_pathological(t, n, m):                      # раздел 3
    if m.startswith("M1"):
        return "IV"
    if t == "Tis" or n == "N3":
        return None                                 # pN3 в системе p16+ нет
    k = t_num(t)
    if k <= 2:
        return "I" if n in ("N0", "N1") else "II"
    return "II" if n in ("N0", "N1") else "III"


def nasopharynx9(t, n, m):                          # раздел 4
    if m == "M1a":
        return "IVA"
    if m == "M1b":
        return "IVB"
    if m == "M1" or t in ("T0", "Tis"):
        return None                                 # нужен M1a/M1b; T0 и Tis — вопрос врачу
    k = t_num(t)
    if k == 4 or n == "N3":
        return "III"
    if k == 3 or n == "N2":
        return "II"
    return "IA" if n == "N0" else "IB"


def stage(data):
    """Возвращает (результат, код возврата)."""
    missing = [f for f in ("site", "T", "N", "M") if not data.get(f)]
    if missing:
        return {"ok": False, "error": f"нет полей: {', '.join(missing)}"}, 2
    site = data["site"]
    if site not in SITES:
        return {"ok": False, "error": f"site из {sorted(SITES)}"}, 2
    t, n, m = norm(data["T"], "T"), norm(data["N"], "N"), norm(data["M"], "M")
    bad = [k for k, v in (("T", t), ("N", n), ("M", m)) if v is None]
    if bad:
        return {"ok": False, "error": f"не распознаны категории: {', '.join(bad)}"}, 2
    notes, basis = [], data.get("basis", "clinical")
    if site == "nasopharynx":
        table, result = "AJCC/UICC v9, носоглотка", nasopharynx9(t, n, m)
    elif site == "oropharynx" and data.get("p16") == "positive":
        if basis not in ("clinical", "pathological"):
            return {"ok": False, "error": "basis: clinical или pathological"}, 2
        table = f"AJCC 8, ротоглотка p16+, {'клиническая' if basis == 'clinical' else 'патологическая'}"
        result = (p16_clinical if basis == "clinical" else p16_pathological)(t, n, m)
    else:
        if site == "oropharynx" and data.get("p16") != "negative":
            notes.append("p16 неизвестен — посчитано по таблице для p16-отрицательных; уточнить p16")
        table, result = "AJCC 8, общая группировка", common(t, n, m)
    if result is None:
        return {"ok": False, "error": f"сочетание {t} {n} {m} не группируется по таблице «{table}» — вопрос врачу",
                "table": table}, 2
    documented = str(data.get("documented_stage") or "").strip().upper().removeprefix("СТАДИЯ ").strip()
    out = {"ok": documented == result, "stage": result, "table": table,
           "input": f"{t} {n} {m}", "documented": documented or None, "notes": notes}
    if data.get("edition") and data["edition"] not in table:
        out["notes"].append(f"в карте указано издание {data['edition']}, расчёт — {table}")
    return out, 0 if out["ok"] else 1


def fail(msg):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    sys.exit(2)


def main(argv):
    if len(argv) != 2:
        fail("ожидался один аргумент: путь к work/staging.json")
    try:
        with open(argv[1], encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        fail(f"файл {argv[1]} не найден: попроси harness положить данные стадирования")
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        fail(f"файл {argv[1]} не JSON в UTF-8: {e}")
    if not isinstance(data, dict):
        fail("вход — JSON-объект с полями site, T, N, M")
    out, code = stage(data)
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(code)


if __name__ == "__main__":
    main(sys.argv)
