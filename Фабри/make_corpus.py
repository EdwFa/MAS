"""Синтетический корпус по болезни Фабри для практикумов 10–12.

    python make_corpus.py

Из src/*.md делает:
  pdf/*.pdf                — учебные протоколы в PDF (с колонтитулами и номерами страниц, как настоящие);
  reference_chunks.jsonl   — эталонная структурная нарезка (пункт = чанк, таблица = чанк);
  labels.csv               — 300 пар «вопрос — фрагмент» с меткой 0/1 (практикум 10);
Вопросы с эталонами — в questions.csv (пишутся вручную), выписки — в выписки/.
Все тексты синтетические и учебные.
"""
import csv
import json
import random
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).resolve().parent
META = re.compile(r"<!--\s*doc:\s*(\S+)\s*\|\s*version:\s*(\S+)\s*\|\s*title:\s*(.+?)\s*-->")
POINT = re.compile(r"^(\d+(?:\.\d+){2,})\s+\S")
SECTION = re.compile(r"^##\s+(\d+(?:\.\d+)?)\s+(.+)$")
PARA_NUM = re.compile(r"^(\d+\.\d+)\s+\S")
GRADE = re.compile(r"^\(УУР [A-C], УДД [1-5]\)$")

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def parse(path):
    """Документ → блоки: section / point / para / table, у каждого номер раздела."""
    text = path.read_text(encoding="utf-8")
    doc, version, title = META.search(text).groups()
    blocks, section, sec_title = [], "", ""
    lines = [l.rstrip() for l in text.splitlines()]
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("<!--") or line.startswith("# "):
            continue
        m = SECTION.match(line)
        if m:
            section, sec_title = m.group(1), m.group(2)
            blocks.append({"type": "section", "id": section, "title": sec_title, "lines": [line[3:]]})
            continue
        if line.startswith("Таблица"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(set(c) <= set("- ") for c in cells):
                    rows.append(cells)
                i += 1
            tid = re.search(r"Таблица (\d+(?:\.\d+)?)", line).group(1)
            blocks.append({"type": "table", "id": f"table-{tid}", "section": section, "caption": line, "rows": rows})
            continue
        if POINT.match(line) or PARA_NUM.match(line):
            pid = (POINT.match(line) or PARA_NUM.match(line)).group(1)
            blocks.append({"type": "point", "id": pid, "section": section, "lines": [line]})
            continue
        if blocks and blocks[-1]["type"] in ("point", "section", "para"):
            if blocks[-1]["type"] == "section" or GRADE.match(line) or line.startswith("Комментарий") \
                    or line.startswith("- ") or blocks[-1]["type"] == "point":
                blocks[-1]["lines"].append(line)
                continue
        blocks.append({"type": "para", "id": section, "section": section, "lines": [line]})
    return doc, version, title, blocks


def chunks_of(doc, title, blocks):
    """Эталонная нарезка: раздел с прозой — один чанк; пункт с оценкой и комментарием — один чанк; таблица — один чанк."""
    out = []
    for b in blocks:
        if b["type"] == "table":
            text = b["caption"] + "\n" + "\n".join(" | ".join(r) for r in b["rows"])
        else:
            text = "\n".join(b["lines"])
        if b["type"] == "section" and len(b["lines"]) == 1:
            continue                                     # голый заголовок — не чанк
        out.append({"id": f"{doc}#{b['id']}", "doc": doc, "title": title,
                    "section": b.get("section", b["id"]), "kind": b["type"], "text": text})
    return out


def pdf(doc, version, title, blocks, path):
    pdfmetrics.registerFont(TTFont("DV", FONT))
    pdfmetrics.registerFont(TTFont("DVB", FONT_B))
    st = {"h1": ParagraphStyle("h1", fontName="DVB", fontSize=15, leading=19, spaceAfter=10),
          "h2": ParagraphStyle("h2", fontName="DVB", fontSize=12, leading=15, spaceBefore=10, spaceAfter=4),
          "p": ParagraphStyle("p", fontName="DV", fontSize=10, leading=13.5, spaceAfter=3),
          "g": ParagraphStyle("g", fontName="DV", fontSize=9, leading=12, textColor=colors.HexColor("#444444"), spaceAfter=3),
          "cap": ParagraphStyle("cap", fontName="DVB", fontSize=9.5, leading=12, spaceBefore=6, spaceAfter=3),
          "td": ParagraphStyle("td", fontName="DV", fontSize=8.5, leading=11)}
    story = [Paragraph(title, st["h1"]),
             Paragraph(f"Версия {version}. Учебный синтетический документ для курса; не для клинических решений.", st["g"])]
    for b in blocks:
        if b["type"] == "section":
            story.append(Paragraph(b["lines"][0], st["h2"]))
            for l in b["lines"][1:]:
                story.append(Paragraph(l, st["p"]))
        elif b["type"] == "table":
            story.append(Paragraph(b["caption"], st["cap"]))
            data = [[Paragraph(c, st["td"]) for c in r] for r in b["rows"]]
            t = Table(data, repeatRows=1)
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(t)
            story.append(Spacer(1, 4))
        else:
            for l in b["lines"]:
                story.append(Paragraph(l, st["g"] if (GRADE.match(l) or l.startswith("Комментарий")) else st["p"]))

    def page(canvas, d):
        canvas.saveState()
        canvas.setFont("DV", 7.5)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(20 * mm, A4[1] - 12 * mm, f"{title} · версия {version}")
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Учебный протокол {doc} · стр. {d.page}")
        canvas.restoreState()

    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                      topMargin=18 * mm, bottomMargin=16 * mm, title=title, author="Кафедра (учебный)").build(
        story, onFirstPage=page, onLaterPages=page)


def norm(s):
    return re.sub(r"\s+", " ", s.replace("­", "")).strip().lower()


def main():
    all_chunks = []
    for src in sorted((HERE / "src").glob("*.md")):
        doc, version, title, blocks = parse(src)
        pdf(doc, version, title, blocks, HERE / "pdf" / f"{doc}.pdf")
        all_chunks += chunks_of(doc, title, blocks)
    with open(HERE / "reference_chunks.jsonl", "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    qs = list(csv.DictReader(open(HERE / "questions.csv", encoding="utf-8")))
    rng = random.Random(42)
    pairs = []
    distract = [c for c in all_chunks if c["section"] in ("1", "3", "4", "6", "7", "8") and c["kind"] != "point"]
    labelled = [q for q in qs if q["kind"] != "none"][:30]
    split = {q["id"]: ("calib" if i % 3 != 2 else "test") for i, q in enumerate(labelled)}
    for q in labelled:
        keys = [k.strip() for k in q["key"].split("||")]
        gold = [c for c in all_chunks if any(norm(k) in norm(c["text"]) for k in keys)]
        same = [c for c in all_chunks if c["doc"] == q["doc"] and c not in gold]
        neg = rng.sample([d for d in distract if d not in gold], 2) + rng.sample(same, min(4, len(same)))
        rest = [c for c in all_chunks if c not in gold and c not in neg]
        cand = (gold + neg + rng.sample(rest, 10))[:10]
        rng.shuffle(cand)
        for c in cand:
            pairs.append({"split": split[q["id"]], "question_id": q["id"], "question": q["question"], "chunk_id": c["id"],
                          "chunk": c["text"], "label": int(c in gold)})
    with open(HERE / "labels.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["split", "question_id", "question", "chunk_id", "chunk", "label"])
        w.writeheader()
        w.writerows(pairs)
    print(f"чанков {len(all_chunks)}, пар {len(pairs)}, положительных {sum(p['label'] for p in pairs)}")


if __name__ == "__main__":
    main()
