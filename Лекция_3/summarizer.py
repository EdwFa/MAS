# summarizer.py
"""Summarizer agent.

Uses a lightweight pure‑Python summarizer (Sumy) to produce a concise summary of
plain‑text content. The library has no native dependencies, so it works on the
current Python 3.13 interpreter without needing Rust toolchains.
"""

import logging
from typing import List

# Sumy imports – pure Python, no compiled extensions
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer

# Дочерний логгер – вывод настраивается у родителя «archiv_tracker» (utils.py)
logger = logging.getLogger("archiv_tracker.summarizer")

def _get_summarizer() -> LsaSummarizer:
    """Create (or retrieve) a Sumy LSA summarizer instance.
    The summarizer is lightweight, so we simply instantiate a new one each
    call – the overhead is negligible for the modest number of articles we
    process.
    """
    summarizer = LsaSummarizer()
    # Optionally adjust summarizer parameters here (e.g., stop words).
    return summarizer

def summarize(text: str, max_sentences: int = 3) -> str:
    """Return a concise summary for *text*.

    Parameters
    ----------
    text: str
        The full article body.
    max_sentences: int, optional
        Maximum number of sentences in the generated summary. Default is 3.

    Returns
    -------
    str
        The generated summary.
    """
    if not text:
        logger.warning("Empty text received for summarization.")
        return ""
    parser = PlaintextParser.from_string(text, Tokenizer("english"))
    summarizer = _get_summarizer()
    summary_sentences = summarizer(parser.document, max_sentences)
    summary = " ".join(str(sentence) for sentence in summary_sentences)
    logger.info("Generated summary (%d sentences).", max_sentences)
    return summary
