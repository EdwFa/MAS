"""pytest -q Лекция_16/starter — неделя задачи NGS за секунды: без сети и без модели."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from a2a_client import A2AClient, A2AError, load_card  # noqa: E402
from chart_write import FakeFHIR, chart_write, compensate  # noqa: E402
from fake_lab import FakeLab  # noqa: E402
from store import CaseStore  # noqa: E402
from workflow import Env, Killed, deadline_note, on_push, resume_case, start_case  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parents[1]
NGS = HERE / "fixtures" / "ngs.json"
WRITE = "urn:mas:write|P-0042/ngs-result"


@pytest.fixture
def world(tmp_path):
    """Всё, что переживает перезапуск агента: база случая, лаборатория, FHIR-сервер больницы."""
    store, lab, fhir = CaseStore(tmp_path / "cases.db"), FakeLab(), FakeFHIR()
    client = A2AClient(lab)
    lab.webhook = lambda req: on_push(req, store, client)
    return store, lab, fhir, client


def env(world, crash_at=()):
    store, lab, fhir, client = world
    return Env(store, client, fhir, load_card(), crash_at)


def kinds(store):
    return [e["kind"] for e in store.events("P-0042")]


# --- слайд 26 -----------------------------------------------------------------

def test_survives_restart(world):
    store, lab, fhir, _ = world
    run = start_case("P-0042", env(world))
    assert run.until("wait_lab") == "wait_lab"
    run.kill()                                         # деплой во вторник
    lab.complete(NGS)
    assert lab.push(times=2) == [200, 200]             # уведомление дважды
    run = resume_case("P-0042", env(world))
    assert run.until("paused_for_doctor") == "paused_for_doctor"
    run.approve(doctor="dr-17")
    assert run.until("done") == "done"
    assert lab.sent_tasks() == 1                       # задачу не отправили снова
    assert len(fhir.search(identifier=WRITE)) == 1     # одна запись
    assert "push.duplicate" in kinds(store)
    assert {"process.killed", "process.resumed"} <= set(kinds(store))


def test_crash_between_send_and_save(world):
    """Задача ушла, а taskId не сохранился: повтор шага — тот же messageId, та же задача."""
    _, lab, _, _ = world
    run = start_case("P-0042", env(world, crash_at={"after_send"}))
    with pytest.raises(Killed):
        run.until("wait_lab")
    run = resume_case("P-0042", env(world))
    assert run.until("wait_lab") == "wait_lab"
    assert lab.sent_tasks() == 1 and run.rec["lab"]["taskId"] == lab.only_task()


def test_crash_between_fhir_and_ledger(world):
    """Запись на сервере есть, в журнале — нет: условное создание не даёт дубля."""
    store, lab, fhir, _ = world
    run = start_case("P-0042", env(world, crash_at={"before_ledger"}))
    run.until("wait_lab")
    lab.complete(NGS)
    lab.push()
    run.until("paused_for_doctor")
    run.approve("dr-17")
    # упадём в write_chart до журнала; сымитируем, что сервер запись уже принял
    rec = run.rec
    fhir.create({"resourceType": "Observation", "identifier": [{"system": "urn:mas:write", "value": "P-0042/ngs-result"}]})
    with pytest.raises(Killed):
        run.until("done")
    run = resume_case("P-0042", env(world))
    assert run.until("done") == "done"
    assert len(fhir.search(identifier=WRITE)) == 1 and rec["case"] == "P-0042"


# --- INPUT_REQUIRED через паузу врача (слайд 13, хронология P-0042) ---------------

def test_input_required_goes_to_doctor(world):
    store, lab, _, _ = world
    run = start_case("P-0042", env(world))
    run.until("wait_lab")
    lab.input_required("Укажите номер блока FFPE; нужна подпись лечащего врача")
    lab.push()
    assert run.until("done") == "paused_for_input"     # модель за врача не отвечает
    assert any("номер блока FFPE" in q for q in run.rec["open_questions"])
    run.kill()                                         # врач в отпуске до пятницы
    run = resume_case("P-0042", env(world))
    assert run.until("done") == "paused_for_input"     # пауза — не таймаут
    run.answer_lab("dr-17", "Блок 26-4417/B2; подтверждено dr-17")
    assert run.until("done") == "wait_lab"
    tid = lab.only_task()
    assert lab.tasks[tid]["status"]["state"] == "TASK_STATE_WORKING"
    reply = lab.tasks[tid]["history"][-1]
    assert reply["messageId"] == "P-0042/ngs/consent" and reply["taskId"] == tid
    assert "doctor_input" not in run.rec               # разрешение — на один ответ


# --- уведомления --------------------------------------------------------------

def test_push_wrong_token_and_unknown_task(world):
    store, lab, _, client = world
    start_case("P-0042", env(world)).until("wait_lab")
    lab.complete(NGS)
    assert lab.push(token="чужой") == [404]
    assert on_push({"headers": {}, "body": {"statusUpdate": {"taskId": "t-0000"}}}, store, client) == 404
    assert "push" not in kinds(store)


def test_push_body_not_trusted(world):
    """Уведомление — повод спросить: состояние берём через GetTask."""
    store, lab, _, _ = world
    start_case("P-0042", env(world)).until("wait_lab")
    lab.complete(NGS)
    lab.push()
    assert lab.requests[-1]["method"] == "GET" and lab.requests[-1]["path"].startswith("/tasks/")


# --- граница и формат ---------------------------------------------------------

def test_every_request_has_version_header(world):
    _, lab, _, _ = world
    run = start_case("P-0042", env(world))
    run.until("wait_lab")
    lab.complete(NGS)
    lab.push()
    assert lab.requests and all(r["headers"].get("A2A-Version") == "1.0" for r in lab.requests)


def test_only_schema_fields_leave(world):
    _, lab, _, _ = world
    start_case("P-0042", env(world)).until("wait_lab")
    out = lab.outbound()
    assert "PSN-7f3a" in out and "P-0042/ngs/1" in out
    for secret in ("Соколова", "1959", "Patient/P-0042", "open_questions"):
        assert secret not in out
    data = lab.tasks[lab.only_task()]["history"][0]["parts"][0]["data"]
    assert set(data) == {"case", "specimen", "panel", "consent"}


def test_card_pin(tmp_path):
    card = load_card()
    assert card["url"] == "https://lab.example/a2a/rest" and "description" not in card
    fake = json.loads((HERE / "lab_card.json").read_text(encoding="utf-8"))
    fake["supportedInterfaces"][0]["url"] = "https://lab-example.evil/a2a/rest"      # подмена адреса
    (tmp_path / "lab_card.json").write_text(json.dumps(fake), encoding="utf-8")
    pin = json.loads((HERE / "lab_pin.json").read_text(encoding="utf-8"))
    (tmp_path / "lab_pin.json").write_text(json.dumps(pin), encoding="utf-8")
    with pytest.raises(ValueError):
        load_card(tmp_path / "lab_pin.json")


def test_artifact_with_advice_rejected(world):
    _, lab, fhir, _ = world
    run = start_case("P-0042", env(world))
    run.until("wait_lab")
    lab.complete(HERE / "fixtures" / "ngs_with_advice.json")
    lab.push()
    assert run.until("done") == "done"
    assert any("не прошёл схему" in q for q in run.rec["open_questions"])
    assert fhir.resources == {}                        # в карту ничего не ушло


# --- сроки, отмена, компенсация -----------------------------------------------

def test_cancel_and_cutoff(world):
    _, lab, _, _ = world
    run = start_case("P-0042", env(world))
    run.until("wait_lab")
    assert deadline_note(run.rec) == f"NGS: результат ожидается, task {lab.only_task()}"
    assert run.withdraw()["lab"]["status"] == "TASK_STATE_CANCELED"


def test_cancel_terminal_is_error(world):
    _, lab, _, client = world
    run = start_case("P-0042", env(world))
    run.until("wait_lab")
    lab.complete(NGS)
    with pytest.raises(A2AError) as e:
        client.cancel(lab.only_task())
    assert e.value.body["error"] == "TaskNotCancelableError"
    assert any("отмена не выполнена" in q for q in run.withdraw()["open_questions"])


def test_compensation_keeps_both(tmp_path):
    store, fhir = CaseStore(tmp_path / "c.db"), FakeFHIR()
    bad = chart_write("P-0042", "ngs-result", {"resourceType": "Observation", "valueString": "p.H1047L"}, fhir, store)
    fixed = compensate("P-0042", "ngs-result", bad, {"resourceType": "Observation", "valueString": "p.H1047R"}, fhir, store)
    assert fhir.resources[bad]["status"] == "entered-in-error" and fhir.resources[fixed]["status"] == "final"
    assert len(fhir.resources) == 2
