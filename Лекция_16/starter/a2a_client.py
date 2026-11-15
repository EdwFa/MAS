"""Клиент A2A 1.0, привязка HTTP+JSON (лекция 16, слайды 6–11, 13, 22, 24).

    POST /message:send       SendMessage
    GET  /tasks/{id}         GetTask
    POST /tasks/{id}:cancel  CancelTask
Заголовок A2A-Version: 1.0 — в каждом запросе: без него сервер считает клиента версией 0.3.

Транспорт — объект с методом request(method, path, body, headers) -> (code, json).
HttpTransport ходит в сеть; FakeLab из fake_lab.py — заглушка для тестов.
Сверяйте детали формата с a2a-protocol.org для версии вашего сервера.
"""
import json
import pathlib
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
VERSION = "1.0"
TERMINAL = {"TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED", "TASK_STATE_REJECTED"}
INTERRUPTED = {"TASK_STATE_INPUT_REQUIRED", "TASK_STATE_AUTH_REQUIRED"}


class A2AError(Exception):
    def __init__(self, code, body):
        super().__init__(f"A2A {code}: {body}")
        self.code, self.body = code, body


def load_card(pin_path=HERE / "lab_pin.json"):
    """Карточка из репозитория, сверенная с закреплёнными адресом и версией (слайд 8).
    Возвращает только то, что нужно коду. description в окно модели не передаётся."""
    pin = json.loads(pathlib.Path(pin_path).read_text(encoding="utf-8"))
    card = json.loads((pathlib.Path(pin_path).parent / pin["card"]).read_text(encoding="utf-8"))
    iface = next((i for i in card["supportedInterfaces"]
                  if i["protocolBinding"] == pin["protocolBinding"] and i["protocolVersion"] == pin["protocolVersion"]),
                 None)
    if iface is None or iface["url"] != pin["url"]:
        raise ValueError("карточка не совпадает с закреплённым адресом или версией — задачу не отправляем")
    if pin["skill"] not in {s["id"] for s in card["skills"]}:
        raise ValueError(f"в карточке нет навыка {pin['skill']}")
    if not card["capabilities"].get("pushNotifications"):
        raise ValueError("лаборатория не поддерживает push: нужен другой способ ждать")
    return {"url": iface["url"], "skill": pin["skill"], "push_url": pin["push_url"], "version": card["version"]}


class HttpTransport:
    def __init__(self, base_url, auth=None, timeout=30):
        self.base, self.auth, self.timeout = base_url.rstrip("/"), auth, timeout

    def request(self, method, path, body, headers):
        h = dict(headers)
        if self.auth:
            h["Authorization"] = self.auth                     # учётные данные — вне текста сообщений
        req = urllib.request.Request(self.base + path, method=method, headers=h,
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")


class A2AClient:
    def __init__(self, transport, trace=None):
        self.t, self.trace = transport, trace

    def _call(self, method, path, body=None):
        headers = {"A2A-Version": VERSION, "Content-Type": "application/a2a+json"}
        code, out = self.t.request(method, path, body, headers)
        if self.trace:
            self.trace("a2a." + path.split("/")[-1].split(":")[-1], code=code)
        if code >= 400:
            raise A2AError(code, out)
        return out

    def send(self, message_id, context_id, data, push_url, push_token, task_id=None):
        """SendMessage. message_id стабилен: повтор отправки — тот же message_id, а не новая задача."""
        msg = {"messageId": message_id, "contextId": context_id, "role": "ROLE_USER", "parts": [{"data": data}]}
        if task_id:
            msg["taskId"] = task_id                            # продолжение той же задачи
        body = {"message": msg,
                "configuration": {"returnImmediately": True,
                                  "pushNotificationConfig": {"url": push_url, "token": push_token}}}
        out = self._call("POST", "/message:send", body)
        return out.get("task", out)

    def get(self, task_id):
        return self._call("GET", f"/tasks/{task_id}")

    def cancel(self, task_id):
        return self._call("POST", f"/tasks/{task_id}:cancel")


def state(task):
    return task["status"]["state"]


def data_parts(artifact):
    return [p["data"] for p in artifact.get("parts", []) if "data" in p]
