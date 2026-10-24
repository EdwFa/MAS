# streamlit_app.py
"""Streamlit-интерфейс мульти-агентного трекера публикаций archive.org.

Возможности:
- Все настройки запуска находятся в боковой панели.
- Кнопка ручного запуска одного цикла обработки (поиск → извлечение текста → резюме).
- Найденные публикации и их резюме выводятся прямо в интерфейс.
- Схема агентов открывается на отдельной вкладке.
- Отправка на почту в тестовом режиме отключена.
"""

import subprocess
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# Импорт основной функции обработки из main.py (файлы лежат в одной папке).
from main import process_items
from scraper import SOURCE_NAMES
from utils import load_config, HISTORY_PATH, get_history, resolve_date_range

st.set_page_config(
    page_title="Трекер публикаций",
    page_icon="📚",
    layout="wide",
)

cfg = load_config()

# ---------------------------------------------------------------------------
# Боковая панель: настройки
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Настройки")

    st.subheader("Поиск")
    topics_text = st.text_area(
        "Темы для отслеживания (по одной в строке)",
        value="\n".join(cfg.get("topics", [])),
        height=120,
        help="По умолчанию берутся из config.yaml. Изменения действуют только в этом сеансе.",
    )
    topics = [t.strip() for t in topics_text.splitlines() if t.strip()]

    available_sources = list(SOURCE_NAMES)
    default_sources = [
        sid for sid in cfg.get("sources", available_sources) if sid in SOURCE_NAMES
    ] or available_sources
    sources = st.multiselect(
        "Подключённые источники",
        options=available_sources,
        default=default_sources,
        format_func=lambda sid: SOURCE_NAMES.get(sid, sid),
        help=(
            "Какие агенты-источники опрашивать. "
            "По умолчанию берутся из config.yaml. Изменения действуют только в этом сеансе."
        ),
    )

    period = st.selectbox(
        "Диапазон дат",
        options=["week", "month", "custom"],
        index=0,
        format_func=lambda key: {
            "week": "Неделя",
            "month": "Месяц",
            "custom": "Произвольный",
        }[key],
        help=(
            "Ограничение по дате в поисковом запросе. "
            "Неделя — последние 7 дней, месяц — с этой даты месяц назад. "
            "Обе границы включаются. По умолчанию — неделя."
        ),
    )
    if period == "custom":
        default_from, default_to = resolve_date_range(preset="week")
        date_from = st.date_input("С", value=default_from)
        date_to = st.date_input("По", value=default_to)
    else:
        date_from, date_to = resolve_date_range(preset=period)
        st.caption(
            f"{date_from.strftime('%d.%m.%Y')} — {date_to.strftime('%d.%m.%Y')}"
        )
    dates_ok = bool(date_from and date_to and date_from <= date_to)
    if not dates_ok:
        st.warning("Дата «С» должна быть не позже даты «По».")

    rows = st.slider(
        "Сколько последних записей запрашивать",
        min_value=5, max_value=100, value=20, step=5,
    )

    st.subheader("Резюме")
    max_sentences = st.slider("Предложений в резюме", 1, 10, 3)
    text_limit = st.slider(
        "Лимит текста страницы (символов)",
        min_value=500, max_value=10000, value=2000, step=500,
        help="Сколько символов текста со страницы передавать агенту-суммаризатору.",
    )

    st.subheader("История")
    skip_seen = st.checkbox(
        "Пропускать уже просмотренные",
        value=False,
        help="Если включено – публикации из history.json не показываются повторно.",
    )
    save_history = st.checkbox(
        "Сохранять найденное в историю",
        value=False,
        help="Для проверки лучше выключить, чтобы одни и те же результаты можно было получать снова.",
    )
    st.caption(f"В истории сейчас записей: **{len(get_history())}**")
    if st.button("🗑 Очистить историю", use_container_width=True):
        HISTORY_PATH.write_text("[]", encoding="utf-8")
        st.success("История очищена.")
        st.rerun()

    st.subheader("Почта")
    st.checkbox(
        "Отправлять резюме на почту",
        value=False,
        disabled=True,
        help="Отключено на время проверки. Результаты выводятся только в интерфейс.",
    )
    st.caption(f"Получатель: {cfg.get('email', {}).get('to_address', '—')}")

    st.subheader("Планировщик")
    st.caption(
        f"Интервал автоматической проверки: "
        f"**{cfg.get('check_interval_seconds', 3600)} с** (задаётся в config.yaml)"
    )

    with st.expander("Полная конфигурация (config.yaml)"):
        safe_cfg = dict(cfg)
        if "email" in safe_cfg:
            safe_cfg["email"] = {
                k: ("••••••" if k == "password" else v)
                for k, v in safe_cfg["email"].items()
            }
        st.json(safe_cfg)

# ---------------------------------------------------------------------------
# Основная область
# ---------------------------------------------------------------------------
st.title("📚 Трекер публикаций")
st.caption(
    "Мульти-агентная система: скрапер → валидатор → извлечение текста → суммаризатор. "
    "🧪 Тестовый режим: письма не отправляются."
)

tab_search, tab_diagram = st.tabs(["🔎 Поиск", "🗺 Схема агентов"])

with tab_search:
    run = st.button(
        "🚀 Запустить поиск сейчас",
        type="primary",
        disabled=not topics or not sources or not dates_ok,
    )
    if not topics:
        st.warning("Укажите хотя бы одну тему в боковой панели.")
    elif not sources:
        st.warning("Подключите хотя бы один источник в боковой панели.")
    elif not dates_ok:
        st.warning("В боковой панели дата «С» должна быть не позже даты «По».")

    if run:
        with st.spinner("Агенты работают: ищем публикации и составляем резюме…"):
            try:
                st.session_state["results"] = process_items(
                    topics=topics,
                    sources=sources,
                    rows=rows,
                    skip_seen=skip_seen,
                    save_history=save_history,
                    max_sentences=max_sentences,
                    text_limit=text_limit,
                    date_from=date_from,
                    date_to=date_to,
                    send=False,  # пока только вывод в интерфейс
                )
                st.session_state["run_error"] = None
            except Exception as e:
                st.session_state["results"] = []
                st.session_state["run_error"] = str(e)

    if st.session_state.get("run_error"):
        st.error(f"Ошибка при обработке: {st.session_state['run_error']}")

    results = st.session_state.get("results")
    if results is not None and not st.session_state.get("run_error"):
        st.header("Найденные публикации")
        with_summary = sum(1 for r in results if r.get("summary"))
        c1, c2, c3 = st.columns(3)
        c1.metric("Найдено", len(results))
        c2.metric("С резюме", with_summary)
        c3.metric("Отправлено на почту", 0)

        if not results:
            st.info(
                "Новых релевантных публикаций не найдено. "
                "Попробуйте выключить «Пропускать уже просмотренные» или изменить темы."
            )
        else:
            tab_cards, tab_table = st.tabs(["🗂 Карточки", "📋 Таблица"])
            with tab_cards:
                for i, r in enumerate(results, start=1):
                    title = r.get("title") or "(без названия)"
                    if isinstance(title, list):
                        title = " ".join(title)
                    with st.expander(f"{i}. {title}", expanded=i <= 3):
                        src = SOURCE_NAMES.get(r.get("source"), r.get("source") or "—")
                        st.markdown(f"🔗 [{r['url']}]({r['url']})")
                        st.markdown(f"**Источник:** {src}")
                        st.markdown(f"**Идентификатор:** `{r['identifier']}`")
                        st.markdown("**Резюме:**")
                        if r.get("summary"):
                            st.write(r["summary"])
                        else:
                            st.caption("Резюме отсутствует.")
                        st.caption(f"Статус: {r.get('status', '')}")
            with tab_table:
                df = pd.DataFrame(results).rename(
                    columns={
                        "source": "Источник",
                        "identifier": "Идентификатор",
                        "title": "Название",
                        "url": "Ссылка",
                        "summary": "Резюме",
                        "status": "Статус",
                    }
                )
                if "Источник" in df.columns:
                    df["Источник"] = df["Источник"].map(
                        lambda sid: SOURCE_NAMES.get(sid, sid)
                    )
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={"Ссылка": st.column_config.LinkColumn("Ссылка")},
                )
    elif results is None:
        st.info("Нажмите «Запустить поиск сейчас», чтобы агенты выполнили один цикл обработки.")

    with st.expander("📜 Последние записи журнала"):
        log_path = Path(__file__).parent / "main.log"
        if log_path.exists():
            try:
                tail = subprocess.check_output(["tail", "-n", "20", str(log_path)])
                st.text(tail.decode())
            except Exception as exc:
                st.warning(f"Не удалось прочитать файл журнала: {exc}")
        else:
            st.caption("Файл журнала не найден — записи выводятся в терминал, где запущен Streamlit.")

with tab_diagram:
    diagram_path = Path(__file__).parent / "diagr" / "agents.html"
    if not diagram_path.is_file():
        st.warning("Файл схемы diagr/agents.html не найден.")
    else:
        components.html(
            diagram_path.read_text(encoding="utf-8"),
            height=900,
            scrolling=True,
        )
