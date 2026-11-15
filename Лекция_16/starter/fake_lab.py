"""Лаборатория-заглушка: сервер A2A в одном процессе (лекция 16, слайд 26).

Отвечает состояниями и артефактом по команде теста. Сети и модели нет.
Ведёт журнал запросов: тест проверяет, что задача ушла один раз и что заголовок версии был всегда.
"""
import itertools
import json
import pathlib

from a2a_client import TERMINAL

STAMPS = itertools.count(1)


class FakeLab:
    def __init__(self):
        self.tasks, self.by_message, self.requests = {}, {}, []
        self.webhook = None                                    # кого звать push-уведомлением
        self._ids = itertools.count(0x81c4)

    # --- сторона сервера A2A ---------------------------------------------
    def request(self, method, path, body, headers):
        self.requests.append({"method": method, "path": path, "body": body, "headers": dict(headers)})
        if headers.get("A2A-Version") != "1.0":
            return 400, {"error": "VersionNotSupportedError"}
        if method == "POST" and path == "/message:send":
            return 200, {"task": self._send(body)}
        if path.startswith("/tasks/"):
            tid = path[len("/tasks/"):].split(":")[0]
            task = self.tasks.get(tid)
            if task is None:
                return 404, {"error": "TaskNotFoundError"}
            if method == "GET":
                return 200, task
            if method == "POST" and path.endswith(":cancel"):
                if task["status"]["state"] in TERMINAL:
                    return 400, {"error": "TaskNotCancelableError"}
                self._set(tid, "TASK_STATE_CANCELED")
                return 200, task
        return 404, {"error": "MethodNotFound"}

    def _send(self, body):
        msg = body["message"]
        if msg["messageId"] in self.by_message:                # повтор того же сообщения — та же задача
            return self.tasks[self.by_message[msg["messageId"]]]
        if msg.get("taskId"):                                  # ответ в существующую задачу
            tid = msg["taskId"]
            self.tasks[tid]["history"].append(msg)
            self.by_message[msg["messageId"]] = tid
            self._set(tid, "TASK_STATE_WORKING")
            return self.tasks[tid]
        tid = f"t-{next(self._ids):x}"
        self.tasks[tid] = {"id": tid, "contextId": msg["contextId"], "history": [msg], "artifacts": [],
                           "status": {"state": "TASK_STATE_SUBMITTED", "timestamp": next(STAMPS)},
                           "push": body["configuration"]["pushNotificationConfig"]}
        self.by_message[msg["messageId"]] = tid
        self._set(tid, "TASK_STATE_WORKING")
        return self.tasks[tid]

    def _set(self, tid, st, message=None):
        self.tasks[tid]["status"] = {"state": st, "timestamp": next(STAMPS),
                                     **({"message": {"role": "ROLE_AGENT", "parts": [{"text": message}]}} if message else {})}

    # --- команды теста -----------------------------------------------------
    def only_task(self):
        assert len(self.tasks) == 1, self.tasks.keys()
        return next(iter(self.tasks))

    def input_required(self, text, tid=None):
        self._set(tid or self.only_task(), "TASK_STATE_INPUT_REQUIRED", text)

    def complete(self, fixture, tid=None):
        tid = tid or self.only_task()
        self.tasks[tid]["artifacts"] = [json.loads(pathlib.Path(fixture).read_text(encoding="utf-8"))]
        self._set(tid, "TASK_STATE_COMPLETED")

    def push(self, times=1, tid=None, token=None):
        """Уведомление «хотя бы раз»: одно и то же событие times раз. Возвращает коды ответа webhook."""
        tid = tid or self.only_task()
        task = self.tasks[tid]
        body = {"statusUpdate": {"taskId": tid, "contextId": task["contextId"], "status": task["status"]}}
        headers = {"X-A2A-Notification-Token": token if token is not None else task["push"]["token"]}
        return [self.webhook({"headers": headers, "body": body}) for _ in range(times)]

    def sent_tasks(self):
        return len(self.tasks)

    def outbound(self):
        """Всё, что ушло к лаборатории, — строкой: для проверки «что уходит за границу»."""
        return json.dumps([r["body"] for r in self.requests if r["body"]], ensure_ascii=False)
