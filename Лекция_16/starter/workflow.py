"""Граф случая NGS с надёжным исполнением (лекция 16, слайды 15–22, 25–26).

Каждый шаг — функция записи случая; после каждого шага запись сохраняется в SQLite.
Процесс можно убить в любой момент: resume_case продолжит с последнего сохранённого шага.
Побочные эффекты (отправка в лабораторию, запись в карту) — отдельными шагами, у каждого свой ключ.

Шаги: start → send_lab → wait_lab → [paused_for_input → reply_lab → wait_lab] →
      paused_for_doctor → write_chart → done
"""
import hmac
import json
import pathlib
import secrets

from jsonschema import Draft202012Validator

from a2a_client import INTERRUPTED, TERMINAL, A2AError, data_parts, state
from chart_write import chart_write

HERE = pathlib.Path(__file__).resolve().parent
NGS = Draft202012Validator(json.loads((HERE / "contracts" / "ngs_result.json").read_text(encoding="utf-8")))
WAIT = {"wait_lab", "paused_for_input", "paused_for_doctor", "done"}


class Killed(Exception):
    """Имитация деплоя: процесс исчез посреди шага."""


def pseudonym(case_id):
    """Псевдоним случая для лаборатории (слайд 12). В учебном коде — из таблицы; в больнице — сервис псевдонимизации."""
    return {"P-0042": "PSN-7f3a"}.get(case_id) or "PSN-" + secrets.token_hex(2)


# --- шаги ---------------------------------------------------------------------

def step_start(rec, env):
    rec["pseudonym"] = pseudonym(rec["case"])
    rec["lab"] = {"contextId": "ctx-" + rec["case"].replace("-", ""), "push_token": secrets.token_urlsafe(16),
                  "taskId": None, "status": None}
    rec.setdefault("open_questions", [])
    return "send_lab"


def step_send_lab(rec, env):
    """Отправить задачу. Повтор этого шага после сбоя — тот же messageId, лаборатория вернёт ту же задачу."""
    task = env.client.send(
        message_id=f'{rec["case"]}/ngs/1', context_id=rec["lab"]["contextId"],
        data={"case": rec["pseudonym"], "specimen": rec["specimen"], "panel": env.card["skill"],
              "consent": rec["consent"]},                           # ровно поля схемы задачи — без ФИО
        push_url=env.card["push_url"], push_token=rec["lab"]["push_token"])
    env.crash_point("after_send")                                   # тест: упасть до сохранения taskId
    rec["lab"].update(taskId=task["id"], status=state(task))
    return "wait_lab"


def step_wait_lab(rec, env):
    st = rec["lab"]["status"]
    if st == "TASK_STATE_INPUT_REQUIRED":
        q = rec["lab"].get("question") or "лаборатория просит уточнение"
        rec["open_questions"].append(f'лаборатория (task {rec["lab"]["taskId"]}): {q}')
        return "paused_for_input"
    if st == "TASK_STATE_AUTH_REQUIRED":
        rec["open_questions"].append("лаборатории нужен доступ: учётные данные передают вне цепочки агентов")
        return "paused_for_input"
    if st == "TASK_STATE_COMPLETED":
        result, problems = check_artifact(rec, rec["lab"].get("artifacts", []))
        rec["result"] = result
        rec["open_questions"] += problems
        return "paused_for_doctor" if result else "done"
    if st in TERMINAL:
        rec["open_questions"].append(f'NGS: задача {rec["lab"]["taskId"]} завершилась {st}')
        return "done"
    return None                                                     # ждём: push или опрос


def step_paused_for_input(rec, env):
    return "reply_lab" if rec.get("doctor_input") else None


def step_reply_lab(rec, env):
    """Ответ врача — новое сообщение в ту же задачу, со своим стабильным messageId."""
    n = rec["lab"].get("replies", 0) + 1                            # каждый ответ — свой ключ
    task = env.client.send(
        message_id=f'{rec["case"]}/ngs/consent' + (f"-{n}" if n > 1 else ""), context_id=rec["lab"]["contextId"], task_id=rec["lab"]["taskId"],
        data={"case": rec["pseudonym"], "answer": rec["doctor_input"]["text"], "confirmed_by": rec["doctor_input"]["doctor"]},
        push_url=env.card["push_url"], push_token=rec["lab"]["push_token"])
    env.crash_point("after_reply")
    rec["lab"].update(status=state(task), replies=n)
    rec["lab"].pop("question", None)
    rec.pop("doctor_input")                                         # разрешение — на один ответ
    return "wait_lab"


def step_paused_for_doctor(rec, env):
    return "write_chart" if rec.get("approved_by") else None


def step_write_chart(rec, env):
    item = rec["result"]["items"][0] if rec["result"]["items"] else None
    resource = {"resourceType": "Observation", "status": "final", "subject": {"reference": f'Patient/{rec["case"]}'},
                "category": [{"text": "pathology"}], "code": {"text": "NGS: " + (item["gene"] if item else "без вариантов")},
                "valueString": f'{item["variant"]}, VAF {item["vaf"]}, tier {item["tier"]}' if item else "варианты не найдены",
                "note": [{"text": "; ".join(rec["result"]["open"])}] if rec["result"]["open"] else [],
                "derivedFrom": [{"display": rec["result"].get("report", "")}],
                "performer": [{"display": f'подтвердил {rec["approved_by"]}'}]}
    env.crash_point("before_ledger")
    rec.setdefault("writes", []).append(chart_write(rec["case"], "ngs-result", resource, env.fhir, env.store))
    return "done"


STEPS = {"start": step_start, "send_lab": step_send_lab, "wait_lab": step_wait_lab,
         "paused_for_input": step_paused_for_input, "reply_lab": step_reply_lab,
         "paused_for_doctor": step_paused_for_doctor, "write_chart": step_write_chart}


def check_artifact(rec, artifacts):
    """Артефакт лаборатории — данные (слайд 14): только по нашей схеме и только для нашего псевдонима."""
    for a in artifacts:
        for d in data_parts(a):
            errors = list(NGS.iter_errors(d))
            if errors:
                return None, [f"NGS: артефакт {a.get('artifactId')} не прошёл схему — {errors[0].message[:120]}"]
            if d["case"] != rec["pseudonym"]:
                return None, ["NGS: артефакт относится к другому случаю"]
            return d, []
    return None, ["NGS: задача завершена, но артефакта с данными нет"]


# --- исполнитель ----------------------------------------------------------------

class Env:
    def __init__(self, store, client, fhir, card, crash_at=()):
        self.store, self.client, self.fhir, self.card = store, client, fhir, card
        self.crash_at = set(crash_at)

    def crash_point(self, name):
        if name in self.crash_at:
            self.crash_at.discard(name)
            raise Killed(name)


class Run:
    """Один процесс агента. kill() — деплой: объект пропадает, запись случая остаётся."""

    def __init__(self, case_id, env):
        self.case, self.env, self.alive = case_id, env, True

    @property
    def rec(self):
        return self.env.store.load(self.case)

    def trace(self, kind, **data):
        self.env.store.event(self.case, kind, **data)

    def until(self, target):
        """Шагать, пока не дойдём до target или до ожидания. Возвращает текущий шаг."""
        assert self.alive, "процесс убит — нужен resume_case"
        while True:
            rec = self.rec
            if rec["step"] == target or rec["step"] == "done":
                return rec["step"]
            nxt = STEPS[rec["step"]](rec, self.env)
            if nxt is None:
                return rec["step"]                                  # ждём внешнего события
            self.trace("step", frm=rec["step"], to=nxt)
            rec["step"] = nxt
            self.env.store.save(rec)                                # контрольная точка после каждого шага

    def kill(self):
        self.alive = False
        self.trace("process.killed")

    def answer_lab(self, doctor, text):
        """Врач отвечает на INPUT_REQUIRED (через паузу, лекция 13)."""
        rec = self.rec
        rec["doctor_input"] = {"doctor": doctor, "text": text}
        self.env.store.save(rec)

    def approve(self, doctor):
        rec = self.rec
        rec["approved_by"] = doctor
        self.env.store.save(rec)

    def withdraw(self):
        """Случай снят с консилиума: CancelTask. Отменить конечную задачу нельзя — это ошибка, а не сбой."""
        rec = self.rec
        try:
            task = self.env.client.cancel(rec["lab"]["taskId"])
            rec["lab"]["status"] = state(task)
        except A2AError as e:
            rec["open_questions"].append(f"отмена не выполнена: {e.body.get('error', e.code)}")
        rec["step"] = "done"
        self.env.store.save(rec)
        return rec


def start_case(case_id, env, specimen="FFPE-2026-1187", consent="DocumentReference/cons-12"):
    env.store.save({"case": case_id, "step": "start", "specimen": specimen, "consent": consent})
    run = Run(case_id, env)
    run.trace("case.start")
    return run


def resume_case(case_id, env):
    run = Run(case_id, env)
    run.trace("process.resumed", step=run.rec["step"])
    return run


def on_push(req, store, client):
    """Приём уведомления (слайд 20). Ответ одинаковый для «нет такой задачи» и «нельзя»."""
    upd = req["body"].get("statusUpdate") or {}
    task_id, stamp = upd.get("taskId"), upd.get("status", {}).get("timestamp")
    rec = store.case_by_task(task_id) if task_id else None
    token = req["headers"].get("X-A2A-Notification-Token", "")
    if rec is None or not hmac.compare_digest(token.encode(), rec["lab"]["push_token"].encode()):
        return 404
    if store.seen_push(task_id, stamp):                            # дубль — норма
        store.event(rec["case"], "push.duplicate", task=task_id, stamp=stamp)
        return 200
    store.event(rec["case"], "push", task=task_id, stamp=stamp)
    task = client.get(task_id)                                     # тело не принимаем на веру
    rec["lab"]["status"] = state(task)
    rec["lab"]["artifacts"] = task.get("artifacts", [])
    if state(task) in INTERRUPTED:
        parts = task["status"].get("message", {}).get("parts", [])
        rec["lab"]["question"] = " ".join(p.get("text", "") for p in parts)[:200]
    store.save(rec)                                                # сначала сохранить, потом шагать
    return 200


def deadline_note(rec):
    """Отсечка (слайд 22): пакет к консилиуму уходит без NGS, задача продолжает жить."""
    if rec.get("step") != "done" or not rec.get("writes"):
        return f'NGS: результат ожидается, task {rec.get("lab", {}).get("taskId")}'
    return None
