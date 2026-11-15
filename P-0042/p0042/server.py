"""MCP-сервер p0042-fhir (лекция 6). Запуск: python -m p0042.server  (stdio).

Ресурсы — чтение карты. Инструменты — расчёт и справочник; запись в карту здесь
намеренно не реализована: в каркасе её выполняет хост после подтверждения врача
(tools.py, политика «спросить»). В MCP 2026-07-28 тот же сценарий делается через
InputRequiredResult — задание практикума.
"""
import json

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .calc import CalcError, egfr as _egfr
from .fhir import FHIRStore

mcp = FastMCP("p0042-fhir")
FHIR = FHIRStore()

REFERENCE = {"креатинин": "женщины 45–84, мужчины 59–104 мкмоль/л (учебные значения)"}


@mcp.resource("fhir://{rtype}/{rid}")
def fhir_read(rtype: str, rid: str) -> str:
    """Запись учебного FHIR по типу и id. Только чтение."""
    return json.dumps(FHIR.read(rtype, rid), ensure_ascii=False)


@mcp.tool
def egfr(sex: str, age: int, creatinine: float, unit: str = "umol/L") -> dict:
    """Расчётная СКФ по CKD-EPI 2021 и категория KDIGO.
    sex: female|male; unit: umol/L|mg/dL. Только взрослые (18+). Расчёт, а не диагноз."""
    try:
        return _egfr(sex, age, creatinine, unit)
    except CalcError as e:
        raise ToolError(str(e)) from None


@mcp.tool
def lab_reference(test: str) -> str:
    """Справочный интервал лабораторного теста (учебный справочник). Только чтение."""
    try:
        return REFERENCE[test.lower()]
    except KeyError:
        raise ToolError(f"нет интервала для «{test}»; известны: {', '.join(REFERENCE)}") from None


@mcp.prompt
def renal_check(case_id: str) -> str:
    """Проверка функции почек перед консилиумом."""
    return (f"Для случая {case_id}: найди последний креатинин в fhir://Observation, "
            "посчитай egfr и укажи дату анализа и ссылку на запись.")


if __name__ == "__main__":
    mcp.run()
