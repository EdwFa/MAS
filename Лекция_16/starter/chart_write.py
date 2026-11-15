"""Идемпотентная запись в карту (лекция 16, слайды 19 и 23).

Два слоя: журнал (быстро) и условное создание FHIR If-None-Exist (если процесс упал
между записью на сервере и записью в журнал). Политику «спросить» это не отменяет:
chart_write вызывают только после подписи врача.
"""
import itertools

SYSTEM = "urn:mas:write"


def chart_write(case_id, step, resource, fhir, ledger):
    """Запись в карту, которую безопасно повторить."""
    key = f"{case_id}/{step}"                # одна запись на шаг
    if (done := ledger.get(key)):            # уже писали —
        return done                          # вернуть то же
    resource["identifier"] = [{"system": SYSTEM, "value": key}]
    ref = fhir.create(resource, if_none_exist=f"identifier={SYSTEM}|{key}")
    ledger.put(key, ref)                     # после ответа сервера
    return ref


def compensate(case_id, step, bad_ref, fixed, fhir, ledger):
    """Сага (слайд 23): ошибку не удаляют — помечают entered-in-error и пишут исправление своим ключом."""
    fhir.mark_entered_in_error(bad_ref)
    return chart_write(case_id, f"{step}/fix", fixed, fhir, ledger)


class FakeFHIR:
    """FHIR-сервер больницы — заглушка с условным созданием. Живёт отдельно от процесса агента."""

    def __init__(self):
        self.resources, self._ids = {}, itertools.count(1)

    def create(self, resource, if_none_exist=None):
        if if_none_exist:
            hit = self.search(identifier=if_none_exist.split("=", 1)[1])
            if hit:
                return hit[0]                  # сервер не создаёт дубль
        rid = f'{resource["resourceType"]}/w-{next(self._ids)}'
        self.resources[rid] = {**resource, "status": resource.get("status", "final")}
        return rid

    def search(self, identifier):
        system, value = identifier.split("|", 1)
        return [rid for rid, r in self.resources.items()
                if any(i["system"] == system and i["value"] == value for i in r.get("identifier", []))]

    def mark_entered_in_error(self, ref):
        self.resources[ref]["status"] = "entered-in-error"
