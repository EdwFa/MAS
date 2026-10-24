# utils.py
"""Utility functions shared across agents.

- Configuration loading (YAML)
- Simple file‑based history store (JSON)
- Central logger configuration
- Helper to fetch and clean text from a URL (used by the main script)
"""

import calendar
import json
import re
import requests
from bs4 import BeautifulSoup
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import yaml

# ---------------------------------------------------------------------------
# Base paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
HISTORY_PATH = BASE_DIR / "history.json"

# ---------------------------------------------------------------------------
# Logger (single shared instance)
# ---------------------------------------------------------------------------
LOG_PATH = BASE_DIR / "main.log"
logger = logging.getLogger("archiv_tracker")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    # Дублируем журнал в файл main.log – его последние строки видны в интерфейсе
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

# ---------------------------------------------------------------------------
# Configuration helper
# ---------------------------------------------------------------------------
def load_config() -> Dict:
    """Load configuration from ``config.yaml``.

    Returns an empty dict if the file does not exist.
    """
    if not CONFIG_PATH.is_file():
        logger.warning(f"Config file not found at {CONFIG_PATH}, returning empty config.")
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_model_settings(engine: str, providers: Dict) -> None:
    """Записать активного провайдера и блоки ``llm`` / ``providers`` в config.yaml."""
    active = providers.get(engine) or providers.get("ollama") or {}
    public_llm = {key: value for key, value in active.items() if value}
    block = "# Чем строить резюме: sumy, ollama или openai.\n" + yaml.safe_dump(
        {"summarizer": engine, "llm": public_llm, "providers": providers},
        allow_unicode=True,
        sort_keys=False,
    )
    text = CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.is_file() else ""
    pattern = re.compile(r"(?ms)^# Чем строить резюме:.*?(?=^# How often to check|\Z)")
    if pattern.search(text):
        text = pattern.sub(block + "\n", text, count=1)
    else:
        text = text.rstrip() + "\n\n" + block
    CONFIG_PATH.write_text(text, encoding="utf-8")


def _subtract_months(day: date, months: int) -> date:
    """Сдвинуть дату на ``months`` назад, ограничив день длиной целевого месяца."""
    month = day.month - months
    year = day.year
    while month <= 0:
        month += 12
        year -= 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last_day))


def resolve_date_range(
    preset: str = "week",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    today: Optional[date] = None,
) -> Tuple[date, date]:
    """Включительные границы поиска.

    ``week`` — с даты 7 дней назад по сегодня, ``month`` — с этой даты
    месяц назад по сегодня. Если заданы обе границы, используется они.
    Иначе по умолчанию берётся неделя.
    """
    today = today or date.today()
    if date_from is not None and date_to is not None:
        return date_from, date_to
    if preset == "month":
        return _subtract_months(today, 1), today
    return today - timedelta(days=7), today


def topic_tokens(topic: str) -> List[str]:
    """Разбить тему так же, как поиск arxiv.org: по пробелам и дефисам.

    «medical multi-agent» → medical, multi, agent. Порядок слов не важен.
    """
    return [part for part in re.split(r"[\s\-]+", topic.strip()) if part]


def token_is_exact(token: str) -> bool:
    """Короткие аббревиатуры вроде RAG ищутся целиком, без префикса."""
    letters = re.sub(r"[^A-Za-z]", "", token)
    return bool(letters) and letters.isupper() and len(letters) <= 5

# ---------------------------------------------------------------------------
# Simple HTML extractor (used by the Streamlit UI and main script)
# ---------------------------------------------------------------------------
def extract_text_from_url(url: str) -> str:
    """Download *url* and return visible text.

    The extractor removes ``script``, ``style`` and ``noscript`` tags and joins the
    remaining strings. It returns an empty string on failure.
    """
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return " ".join(soup.stripped_strings)
    except Exception as e:
        logger.error(f"Failed to extract text from {url}: {e}")
        return ""

# ---------------------------------------------------------------------------
# History handling (stores processed identifiers to avoid repeats)
# ---------------------------------------------------------------------------
def _ensure_history_file():
    if not HISTORY_PATH.is_file():
        HISTORY_PATH.write_text(json.dumps([]), encoding="utf-8")

def get_history() -> List[str]:
    """Return a list of previously processed identifiers.
    """
    _ensure_history_file()
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"Failed to read history file: {e}")
        return []

def update_history(new_ids: List[str]):
    """Append new identifiers to the history file, respecting ``history_size``.
    """
    cfg = load_config()
    max_size = cfg.get("history_size", 1000)
    history = get_history()
    history.extend(new_ids)
    # Deduplicate while preserving order (newest at end)
    seen = set()
    deduped = []
    for item in history:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    # Trim to ``max_size`` (keep most recent entries)
    if len(deduped) > max_size:
        deduped = deduped[-max_size:]
    try:
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(deduped, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to write history file: {e}")
