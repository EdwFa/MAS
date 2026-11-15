"""Модульный RAG (лекция 8): нарезка по структуре, гибридный поиск, RRF, отбор.

Эмбеддер и переранжировщик внедряются. По умолчанию стоят простые заглушки без
внешних моделей — чтобы тесты шли без сети. На практикуме их заменяют локальными
моделями (эмбеддер и кросс-энкодер), не трогая остальной код.
"""
import math
import re
import zlib
from collections import Counter

from . import DATA

HEAD = re.compile(r"^(\d+(?:\.\d+){2,})\s+\S")      # пункт: 3.2.1
TITLE = re.compile(r"^(\d+(?:\.\d+)?)\s+(\S.*)$")    # заголовок: 3 или 3.2
GRADE = re.compile(r"^\(УУР [A-C], УДД [1-5]\)$")
META = re.compile(r"<!--\s*doc:\s*(\S+)\s*\|\s*version:\s*(\S+)\s*\|\s*status:\s*(\S+)\s*-->")
WORD = re.compile(r"[\w-]+")


def chunk_guideline(text, doc_id, version, max_chars=1500):
    """Кусок = пункт рекомендаций вместе с оценкой.
    Заголовки разделов не становятся кусками: они идут в поле title каждого пункта
    (это помогает поиску и ссылке в ответе)."""
    chunks, section, buf, titles = [], "", [], {}

    def flush():
        if buf:
            title = " / ".join(titles[k] for k in sorted(titles))
            chunks.append({"text": " ".join(buf), "section": section, "title": title,
                           "doc": doc_id, "version": version,
                           "graded": any(GRADE.match(x) for x in buf)})   # пункт без УУР/УДД — видно сразу
            buf.clear()

    for line in filter(None, map(str.strip, text.splitlines())):
        if line.startswith("<!--"):
            continue
        if GRADE.match(line):          # оценку не отрываем
            buf.append(line)
            continue
        t = TITLE.match(line)
        if t and not HEAD.match(line):
            flush()
            level = t.group(1).count(".")
            titles = {k: v for k, v in titles.items() if k < level}
            titles[level] = line
            section = ""
            continue
        m = HEAD.match(line)
        too_long = sum(map(len, buf)) + len(line) > max_chars and not line.startswith("|")  # таблицу не рвём
        if m or too_long:
            flush()
            section = m.group(1) if m else section
        buf.append(line)
    flush()
    return chunks


def tokens(text):
    """Грубая нормализация для русского: нижний регистр и первые 6 букв слова."""
    return [w[:6] for w in WORD.findall(text.lower())]


def hashed_embed(text, dim=256):
    """Заглушка эмбеддера: мешок триграмм символов. Заменить локальной моделью."""
    v = [0.0] * dim
    t = " " + text.lower() + " "
    for i in range(len(t) - 2):
        v[zlib.crc32(t[i:i + 3].encode()) % dim] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def overlap_rerank(query, text):
    """Заглушка переранжировщика: доля слов запроса, найденных в куске (0..1)."""
    q = set(tokens(query))
    return len(q & set(tokens(text))) / len(q) if q else 0.0


def rrf(rankings, k=60):
    """Reciprocal Rank Fusion: сумма 1 / (k + ранг)."""
    score = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            score[doc_id] = score.get(doc_id, 0) + 1 / (k + rank)
    return sorted(score, key=score.get, reverse=True)


def select(query, candidates, rerank, budget=4000, min_score=0.3):
    """Оставляем лучшие куски, пока хватает места."""
    scored = sorted(((rerank(query, c["text"]), c) for c in candidates),
                    key=lambda sc: sc[0], reverse=True)
    picked, used = [], 0
    for score, c in scored:
        if score < min_score:
            break
        if used + len(c["text"]) > budget:
            continue
        picked.append({**c, "score": round(score, 2)})
        used += len(c["text"])
    return picked


class Index:
    def __init__(self, files=None, embed=hashed_embed, rerank=overlap_rerank):
        self.embed, self.rerank = embed, rerank
        self.chunks = []
        for path in files or sorted(DATA.glob("guidelines*.md")):
            text = path.read_text(encoding="utf-8")
            doc, version, status = META.search(text).groups()
            for c in chunk_guideline(text, doc, version):
                c.update(id=f"{doc}@{version}#{c['section']}", status=status)
                self.chunks.append(c)
        self.by_id = {c["id"]: c for c in self.chunks}
        self.meta = {c["id"]: {"status": c["status"]} for c in self.chunks}
        self._tf = {c["id"]: Counter(tokens(c["title"] + " " + c["text"])) for c in self.chunks}
        self._len = {i: sum(tf.values()) for i, tf in self._tf.items()}
        self._avg = sum(self._len.values()) / max(len(self._len), 1)
        self._df = Counter(t for tf in self._tf.values() for t in tf)
        self._vec = {c["id"]: self.embed(c["title"] + " " + c["text"]) for c in self.chunks}

    def bm25(self, query, top, k1=1.5, b=0.75):
        n = len(self.chunks)
        scores = {}
        for i, tf in self._tf.items():
            s = 0.0
            for t in tokens(query):
                if t in tf:
                    idf = math.log(1 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5))
                    s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * self._len[i] / self._avg))
            if s > 0:
                scores[i] = s
        return sorted(scores, key=scores.get, reverse=True)[:top]

    def dense(self, query, top):
        q = self.embed(query)
        sim = {i: sum(a * b for a, b in zip(q, v)) for i, v in self._vec.items()}
        return sorted(sim, key=sim.get, reverse=True)[:top]

    def hybrid_search(self, query, top=20):
        """Ищем двумя способами только среди действующих версий."""
        active = {i for i, m in self.meta.items() if m["status"] == "active"}
        lex = [i for i in self.bm25(query, top * 2) if i in active]
        sem = [i for i in self.dense(query, top * 2) if i in active]
        return rrf([lex, sem])[:top]

    def parent(self, chunk_id):
        """«Малое — большое»: пункт 3.2.1 → весь раздел 3.2 той же версии."""
        c = self.by_id[chunk_id]
        prefix = ".".join(c["section"].split(".")[:2])
        same = [x for x in self.chunks if x["doc"] == c["doc"] and x["version"] == c["version"]
                and x["section"].startswith(prefix + ".")]
        return {**c, "text": " ".join(x["text"] for x in same)}

    def answer_context(self, query, budget=4000):
        ids = self.hybrid_search(query)
        return select(query, [self.by_id[i] for i in ids], self.rerank, budget=budget)
