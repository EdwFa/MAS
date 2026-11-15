"""pytest Фабри/test_corpus.py — корпус собран и согласован."""
import csv, json, re
from pathlib import Path
from pypdf import PdfReader

H = Path(__file__).resolve().parent
norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()
CH = [json.loads(l) for l in open(H / "reference_chunks.jsonl", encoding="utf-8")]
QS = list(csv.DictReader(open(H / "questions.csv", encoding="utf-8")))


def test_pdfs_exist_and_marked_synthetic():
    for d in ("fd-diag", "fd-treat", "fd-monitor"):
        text = " ".join(p.extract_text() for p in PdfReader(H / "pdf" / f"{d}.pdf").pages)
        assert "Учебный синтетический документ" in text


def test_reference_chunks_short():
    # 512 токенов e5 ≈ 1500 символов русского текста; эталон с запасом
    assert max(len(c["text"]) for c in CH) < 1500


def test_gold_exists_and_unique():
    ids = {c["id"] for c in CH}
    for q in QS:
        if q["kind"] == "none":
            continue
        assert q["gold"] and set(q["gold"].split(";")) <= ids, q["id"]
        for k in q["key"].split("||"):
            hits = [c for c in CH if norm(k) in norm(c["text"])]
            assert len(hits) == 1, (q["id"], k)


def test_forty_questions():
    assert len(QS) == 40 and sum(q["kind"] == "none" for q in QS) == 3


def test_labels():
    rows = list(csv.DictReader(open(H / "labels.csv", encoding="utf-8")))
    assert len(rows) == 300
    assert sum(r["split"] == "calib" for r in rows) == 200
    assert {r["label"] for r in rows} == {"0", "1"}


def test_lecture_facts():
    t = " ".join(c["text"] for c in CH)
    assert "мигаластат 123 мг внутрь через день" in t
    assert "мигаластат при СКФ ниже 30" in t
    for noise in ("3", "4", "7", "8"):
        assert any(c["doc"] == "fd-diag" and c["section"] == noise for c in CH)
