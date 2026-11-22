---
name: package-check
description: >-
  Проверяет пакет к онкологическому консилиуму:
  обязательные поля, ссылки FHIR, спор дат.
  Use when the user asks to check, validate or
  review a board package («проверь пакет»,
  «всё ли заполнено», «готов ли пакет»).
  Не для сборки пакета и не для записи в карту.
license: Apache-2.0
metadata:
  owner: кафедра онкологии
  version: "1.2"
---
# Проверка пакета к консилиуму

## Шаги
1. Пакет случая лежит в work/package.json — его кладёт harness.
2. Запусти: run_script со script = scripts/check.py и file = work/package.json.
3. Если ok = false и есть problems — перечисли их врачу.
   Ничего не исправляй сам.
   Если есть error (код 2) — пакет не прочитан: скажи об этом врачу
   и не делай вывод о полноте пакета.
4. Если в пакете две даты консилиума — не выбирай,
   вынеси спор в open_questions.
5. В final укажи verdict: "ok" или "problems".

## Нельзя
- Записывать в карту: это chart_write, политика «спросить».
- Придумывать board_date. «Не назначена» — допустимо.

Описание полей — references/fields.md (читай, если врач спросит про поле).
Скрипт исполняй, не читай: нужен его JSON, а не код. Зависимости — только Python 3.
