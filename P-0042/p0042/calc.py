"""Детерминированные расчёты (лекция 6). Модель их не считает — только вызывает."""

KDIGO = ((90, "G1"), (60, "G2"), (45, "G3a"), (30, "G3b"), (15, "G4"))


class CalcError(ValueError):
    """Ошибка входа: сообщение уходит модели как результат с isError."""


def kdigo(gfr):
    return next((c for low, c in KDIGO if gfr >= low), "G5")


def egfr(sex, age, creatinine, unit="umol/L"):
    """Расчётная СКФ по CKD-EPI 2021 (без расового коэффициента) и категория KDIGO.
    Только взрослые (18+). Расчёт, а не диагноз."""
    if sex not in ("female", "male"):
        raise CalcError("sex: только 'female' или 'male'")
    if unit not in ("umol/L", "mg/dL"):
        raise CalcError("unit: только 'umol/L' или 'mg/dL'")
    if age < 18:
        raise CalcError("уравнение только для взрослых: age >= 18")
    scr = creatinine / 88.4 if unit == "umol/L" else creatinine
    if not 0.05 <= scr <= 40:
        raise CalcError(f"креатинин {scr:.2f} мг/дл вне 0,05–40")
    k, a = (0.7, -0.241) if sex == "female" else (0.9, -0.302)
    gfr = (142 * min(scr / k, 1) ** a * max(scr / k, 1) ** -1.2
           * 0.9938 ** age * (1.012 if sex == "female" else 1))
    return {"egfr": round(gfr), "unit": "мл/мин/1,73 м²", "kdigo": kdigo(gfr)}
