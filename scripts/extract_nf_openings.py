"""Извлекает таблицы «Гостиницы / Апарт-отели, открытые в …» из обзоров NF Group.

Что делает:
  1. На нужной странице находит заголовок таблицы (жирные «Название», «Адрес»,
     «Район», «Категория», «Номерной», «Проектный», «Формат») и по нему —
     границы колонок по оси x.
  2. Каждую строку таблицы «якорит» по числу в колонке «Номерной фонд»:
     в каждой строке оно ровно одно. Ячейки бывают в 2–3 строки текста,
     поэтому граница между строками таблицы — середина между соседними якорями.
  3. Склеивает слова каждой ячейки. Перенос «Красногвардей- ский» -> «Красногвардейский».
  4. Категорию разбирает так: «4★ (заявлено)» -> category=4, category_status=заявлена.
     «Без звезд (3★ заявлено)» -> category=3, category_status=заявлена.
  5. Пишет data/clean/nf_openings.csv: один объект = одна строка.

Запуск:  .venv/bin/python scripts/extract_nf_openings.py
"""

import csv
import re
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "clean" / "nf_openings.csv"

TABLES = [
    # source_id, файл, страница, заголовок таблицы, период, формат по умолчанию, список полный?
    ("S1", "S1_NF_Group_SPb_hotels_2025.pdf", 3, "Гостиницы, открытые", "2025", "Гостиница", "да"),
    ("S1", "S1_NF_Group_SPb_hotels_2025.pdf", 4, "Апарт-отели, открытые", "2025", "Апарт-отель", "да"),
    ("S2", "S2_NF_Group_SPb_hotels_H1_2025.pdf", 4, "Апарт-отели, открытые", "2025-H1", "Апарт-отель", "да"),
    ("S3", "S3_NF_Group_SPb_hotels_2024.pdf", 3, "Гостиницы, открытые", "2024", "Гостиница", "да"),
    ("S3", "S3_NF_Group_SPb_hotels_2024.pdf", 4, "Наиболее значимые", "2024", "Апарт-отель", "нет"),
]

HEADERS = {"Название": "name", "Формат": "format", "Адрес": "address", "Район": "district",
           "Категория": "category", "Номерной": "rooms", "Проектный": "project_units"}
MARGIN = 8  # значения в колонке могут начинаться чуть левее заголовка


def join_words(words):
    """Склеивает слова ячейки в порядке чтения, убирая переносы."""
    words = sorted(words, key=lambda w: (round(w["top"]), w["x0"]))
    text = ""
    for w in words:
        t = w["text"].replace("\uf0b6", "").strip()  # \uf0b6 — значок звезды
        if not t:
            continue
        if text.endswith("-") and t[:1].islower():
            text = text[:-1] + t          # перенос слова
        elif text.endswith("-"):
            text += t                     # «Римского-» + «Корсакова»
        else:
            text = f"{text} {t}" if text else t
    return text.strip()


def parse_category(text):
    digits = re.findall(r"\d", text)
    if not digits:
        return None, None
    status = "заявлена" if "заявлено" in text else "присвоена"
    return int(digits[0]), status


def extract(pdf_path, page_no, title):
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_no - 1]
        words = page.extract_words(extra_attrs=["fontname"])

    # Заголовок таблицы: первое слово title, за которым на той же строке идёт второе
    first, second = title.split()[:2]
    t = [w for i, w in enumerate(words)
         if w["text"] == first and i + 1 < len(words) and words[i + 1]["text"] == second]
    top = t[-1]["bottom"]
    head = [w for w in words if "Bold" in w["fontname"] and w["text"] in HEADERS
            and top < w["top"] < top + 40]
    cols = sorted(((w["x0"] - MARGIN, HEADERS[w["text"]]) for w in head))
    head_bottom = max(w["bottom"] for w in head) + 6
    end = min(w["top"] for w in words if w["text"] == "Источник:" and w["top"] > head_bottom)

    def col_of(w):
        name = None
        for x, c in cols:
            if w["x0"] >= x:
                name = c
        return name

    body = [w for w in words if head_bottom < w["top"] < end]
    anchors = sorted((w for w in body if col_of(w) == "rooms" and w["text"].isdigit()),
                     key=lambda w: w["top"])
    mids = [(a["top"] + b["top"]) / 2 for a, b in zip(anchors, anchors[1:])]
    bounds = [head_bottom] + mids + [end]

    rows = []
    for lo, hi in zip(bounds, bounds[1:]):
        cells = {}
        for w in body:
            if lo <= w["top"] < hi:
                cells.setdefault(col_of(w), []).append(w)
        rows.append({c: join_words(ws) for c, ws in cells.items()})
    return rows


def main():
    out = []
    for sid, fname, page_no, title, period, default_format, complete in TABLES:
        for r in extract(RAW / fname, page_no, title):
            cat, status = parse_category(r.get("category", ""))
            out.append({
                "source_id": sid,
                "period": period,
                "name": r["name"],
                "format": r.get("format", default_format),
                "address": r["address"],
                "district": r["district"],
                "category": cat,
                "category_status": status,
                "rooms": int(r["rooms"]),
                "project_units": int(r["project_units"].replace(" ", "")) if r.get("project_units") else None,
                "list_complete": complete,
            })

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"{OUT.relative_to(ROOT)}: {len(out)} строк")


if __name__ == "__main__":
    main()
