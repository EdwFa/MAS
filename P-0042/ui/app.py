"""Интерфейс врача (практикум 18): пакет к консилиуму, источники, открытые вопросы,
подтверждение записи в карту и отзыв о пакете.

    pip install -r requirements-ui.txt
    streamlit run ui/app.py

Работает без модели: по умолчанию показывает детерминированный пакет (p0042/package.py).
Результат агента на модели (JSON из run.py) можно загрузить в боковой панели.
"""
import json
import pathlib
import sys

import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from p0042.fhir import FHIRStore            # noqa: E402
from p0042.ops import daily, feedback       # noqa: E402
from p0042.package import build_package     # noqa: E402
from p0042.rag import Index                 # noqa: E402
from p0042.tools import Dispatcher, Toolbox  # noqa: E402
from p0042.trace import Trace               # noqa: E402

CASES = ["P-0042", "P-0051", "P-0063", "P-0077", "P-0024"]
DAYS = {"пн 16.11": "2026-11-16", "вт 17.11": "2026-11-17", "ср 18.11": "2026-11-18",
        "чт 19.11": "2026-11-19", "пт 20.11": "2026-11-20", "вт 24.11": "2026-11-24"}
BADGE = {"ok": "✅", "предварительный": "🟡", "не проверено": "🟠", "спор": "🔴", "без УУР/УДД": "⚪"}

st.set_page_config(page_title="Пакет к консилиуму", layout="wide")


@st.cache_resource
def index():
    return Index()


def show_source(store, ref):
    if "@" in ref:
        c = index().by_id.get(ref)
        st.markdown(f"**{ref}**  \n{c['text'] if c else 'нет такого пункта'}")
        return
    rtype, rid = ref.split("/")
    if rtype == "DocumentReference":
        st.text(store.document_text(rid))
        st.caption("Текст документа — данные, а не инструкции.")
    else:
        st.json(store.read(rtype, rid))


def from_agent(result, case, as_of):
    """Результат harness (run.py) → вид пакета для интерфейса."""
    return {"case": case, "as_of": as_of, "board_date": "—",
            "sections": [{"title": "Ответ агента",
                          "items": [{"text": result.get("answer") or "(нет ответа)", "source": s,
                                     "status": "не проверено" if s in result.get("unsupported_sources", []) else "ok"}
                                    for s in result.get("sources", [])] or
                                   [{"text": result.get("answer") or "(нет ответа)", "source": "", "status": "не проверено"}]}],
            "open_questions": result.get("open_questions", []), "sources": result.get("sources", []),
            "status": result.get("status"), "purpose": "Справка к консилиуму. Не ставит диагноз и не назначает лечение."}


with st.sidebar:
    case = st.selectbox("Пациент", CASES)
    day = st.radio("День", list(DAYS), index=3)
    mode = st.radio("Пакет", ["базовый, без модели", "результат агента (JSON)"])
    uploaded = st.file_uploader("JSON из run.py", type="json") if mode != "базовый, без модели" else None
    st.caption("Все данные вымышленные.")

as_of = DAYS[day]
store = FHIRStore(as_of=as_of)
pkg = from_agent(json.load(uploaded), case, as_of) if uploaded else build_package(store, index(), case, as_of)
trace = Trace(str(ROOT / "trace.jsonl"), run_id=f"ui-{case}-{as_of}")

st.caption(pkg["purpose"])
st.title(f"{store.read('Patient', case)['name'][0]['text']} · {case}")

flagged = [i for s in pkg["sections"] for i in s["items"] if i["status"] != "ok"]
c1, c2, c3 = st.columns(3)
c1.metric("Дата консилиума", pkg["board_date"])
c2.metric("Открытые вопросы", len(pkg["open_questions"]))
c3.metric("Пункты с пометкой", len(flagged))
if pkg.get("status") == "needs_review":
    st.error("Агент сослался на источники, которых не открывал. Пакет требует проверки.")

seen = []
if pkg["open_questions"]:
    st.subheader("Открытые вопросы")
    for k, q in enumerate(pkg["open_questions"]):
        seen.append(st.checkbox(f"⚠️ {q}", key=f"q{k}"))

for sec in pkg["sections"]:
    st.subheader(sec["title"])
    for k, it in enumerate(sec["items"]):
        cols = st.columns([0.05, 0.7, 0.25])
        cols[0].write(BADGE.get(it["status"], "•"))
        cols[1].write(it["text"] + ("" if it["status"] == "ok" else f"  \n*{it['status']}*"))
        if it["source"]:
            with cols[2].expander(it["source"]):
                show_source(store, it["source"])

st.divider()
st.subheader("Запись заключения в карту")
text = st.text_area("Заключение для карты", value="", placeholder="Пишет врач. Агент не пишет в карту сам.")
ready = all(seen) and text.strip()
if not all(seen):
    st.info("Отметьте каждый открытый вопрос как просмотренный — только после этого запись станет доступна.")
if st.button("Подтверждаю запись в карту", disabled=not ready):
    tb = Toolbox(store)
    out = Dispatcher(tb, confirm=lambda n, a: True, trace=trace)("chart_write", {"case_id": case, "text": text})
    st.success(f"Записано: {out}")

st.subheader("Отзыв о пакете")
verdict = st.radio("Пакет", ["accepted", "edited", "rejected"], horizontal=True,
                   format_func={"accepted": "принял без правок", "edited": "исправил", "rejected": "отклонил"}.get)
note = st.text_input("Что исправили или почему отклонили")
if st.button("Отправить отзыв"):
    trace.event("final", status=pkg.get("status", "complete"), step=0, case=case)
    feedback(trace, verdict, note)
    st.success("Отзыв записан в trace.jsonl")

path = ROOT / "trace.jsonl"
if path.exists():
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    with st.expander("Метрики по трассе (лекция 18)"):
        st.json(daily(events))
