"""Правило двух (Meta, 2025; лекция 17, слайды 7–8).

В одной сессии агент совмещает не больше двух свойств из трёх:
A — недоверенный вход, B — данные пациента, C — действие (запись или канал наружу).
Третье «да» допустимо только с надзором — и надзор должен быть назван.
"""
import csv

NO = {"", "нет", "no"}


def check(path):
    problems = []
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            props = sum(row[k].strip().lower() not in NO for k in ("untrusted_input", "patient_data", "action"))
            if props == 3 and not row["oversight"].strip():
                problems.append(f"{row['agent']}: все три свойства, надзор не указан")
    return problems
