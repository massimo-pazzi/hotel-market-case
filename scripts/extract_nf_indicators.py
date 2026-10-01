"""Извлекает таблицу «Основные показатели. Динамика» из обзоров NF Group (S1–S3).

Что делает:
  1. Открывает PDF из data/raw/ и берёт страницу 2 (там таблица во всех трёх обзорах).
  2. Находит заголовок таблицы (жирные «2025 / 2024 / Динамика») и по нему —
     x-координаты трёх колонок.
  3. Собирает слова ниже заголовка в строки по координате y. В строке таблицы
     есть число в колонке текущего периода, прошлого периода и изменение.
  4. Знак изменения в PDF нарисован стрелкой: в выпусках 2024–2025 гг. —
     символом шрифта Webdings («5» = рост, «6» = снижение), в выпуске 2023 г. —
     обычными «▲»/«▼». Скрипт ставит минус там, где стрелка вниз, — в тексте
     PDF знака минуса часто нет.
  5. Строки сопоставляются с показателями по порядку (он одинаковый во всех
     обзорах; в S3 нет строки про российских операторов).
  6. Пишет data/clean/nf_key_indicators.csv в «длинном» формате:
     одна строка = один показатель за один период.

Запуск:  .venv/bin/python scripts/extract_nf_indicators.py
"""

import csv
import re
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "clean" / "nf_key_indicators.csv"

# (код, название, единица)
M = {
    "rooms_total": ("Номерной фонд в качественных средствах размещения", "номеров"),
    "rooms_hotels": ("Номерной фонд в гостиницах", "номеров"),
    "rooms_apart": ("Номерной фонд в апарт-отелях", "номеров"),
    "new_rooms_total": ("Введено в эксплуатацию за период", "номеров"),
    "new_rooms_hotels": ("Введено: гостиницы", "номеров"),
    "new_rooms_apart": ("Введено: апарт-отели", "номеров"),
    "rooms_intl_operators": ("Номерной фонд под управлением международных операторов", "номеров"),
    "rooms_ru_operators": ("Номерной фонд под управлением российских операторов", "номеров"),
    "occupancy": ("Средняя загрузка номерного фонда", "%"),
    "adr": ("Средняя стоимость номера (ADR)", "руб./сутки"),
    "revpar": ("Средний доход на номер (RevPAR)", "руб./сутки"),
}
ORDER_FULL = list(M)
ORDER_S3 = [m for m in ORDER_FULL if m != "rooms_ru_operators"]
# S9 (выпуск за 2023 г.): нет строки про российских операторов; строка про
# международных операторов считает только гостиницы (без апарт-отелей)
ORDER_S9 = ORDER_S3

REPORTS = [
    # source_id, файл, текущий период, прошлый период, тип периода, порядок строк
    ("S1", "S1_NF_Group_SPb_hotels_2025.pdf", "2025", "2024", "год", ORDER_FULL),
    ("S2", "S2_NF_Group_SPb_hotels_H1_2025.pdf", "2025-H1", "2024-H1", "полугодие", ORDER_FULL),
    ("S3", "S3_NF_Group_SPb_hotels_2024.pdf", "2024", "2023", "год", ORDER_S3),
    ("S9", "S9_NF_Group_SPb_hotels_2023.pdf", "2023", "2022", "год", ORDER_S9),
]
ARROW_DOWN = {"6", "▼"}
ARROWS = {"▲", "▼"}

ROW_TOL = 5  # слова, чьи top отличаются меньше чем на 5 pt, — одна строка


def num(text):
    """'24 902' -> 24902.0; '63,7%' -> 63.7; '2,5x' -> 2.5"""
    t = text.replace("−", "-").replace(" ", "").replace("%", "").replace("x", "")
    return float(t.replace(",", "."))


def extract(pdf_path, order):
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[1]
        words = page.extract_words(extra_attrs=["fontname"])

    # Заголовок: слово «Динамика», левее которого на той же строке стоят два года
    def years_left_of(h):
        return sorted((w for w in words if abs(w["top"] - h["top"]) < 2 and w["x1"] < h["x0"]
                       and re.fullmatch(r"\d{4}", w["text"])), key=lambda w: w["x0"])
    head = next(w for w in words if w["text"].startswith("Динамика") and len(years_left_of(w)) >= 2)
    years = years_left_of(head)[-2:]
    x_cur, x_prev, x_dyn = years[0]["x0"] - 15, years[1]["x0"] - 15, head["x0"] - 15

    # Слова правее начала числовых колонок и ниже заголовка
    body = [w for w in words if w["x0"] >= x_cur and w["top"] > head["bottom"]]
    body.sort(key=lambda w: (w["top"], w["x0"]))

    rows = []
    for w in body:
        if rows and abs(w["top"] - rows[-1][0]["top"]) <= ROW_TOL:
            rows[-1].append(w)
        else:
            rows.append([w])

    result = []
    for row in rows:
        cur = " ".join(w["text"] for w in row if x_cur <= w["x0"] < x_prev)
        prev = " ".join(w["text"] for w in row if x_prev <= w["x0"] < x_dyn)
        is_arrow = lambda w: "Webdings" in w["fontname"] or w["text"] in ARROWS
        dyn_words = [w for w in row if w["x0"] >= x_dyn and not is_arrow(w)]
        arrow = [w["text"] for w in row if is_arrow(w)]
        if not re.search(r"\d", cur) or not re.search(r"\d", prev):
            continue  # это не строка таблицы (сноска и т. п.)
        dyn = " ".join(w["text"] for w in dyn_words)
        result.append((cur, prev, dyn, arrow[0] if arrow else None))
        if len(result) == len(order):
            break

    if len(result) != len(order):
        raise ValueError(f"{pdf_path.name}: найдено {len(result)} строк, ждали {len(order)}")
    return [(order[i],) + r for i, r in enumerate(result)]


def parse_change(dyn, arrow):
    """Возвращает (значение со знаком, единица) для колонки «Динамика»."""
    t = dyn.replace("−", "-").strip()
    if t in ("", "-", "–"):
        return None, None
    unit = "п.п." if "п." in t else ("x" if t.endswith("x") else "%")
    value = num(re.sub(r"п\.\s*п\.", "", t))
    if arrow in ARROW_DOWN and value > 0:   # стрелка вниз, а минуса в тексте нет
        value = -value
    return value, unit


def main():
    out_rows = []
    for sid, fname, cur_p, prev_p, ptype, order in REPORTS:
        for metric, cur, prev, dyn, arrow in extract(RAW / fname, order):
            name, unit = M[metric]
            ch, ch_unit = parse_change(dyn, arrow)
            out_rows.append([sid, cur_p, cur_p, ptype, metric, name, unit, num(cur), ch, ch_unit])
            out_rows.append([sid, cur_p, prev_p, ptype, metric, name, unit, num(prev), None, None])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source_id", "report_period", "period", "period_type", "metric",
                    "metric_name", "unit", "value", "change_reported", "change_unit"])
        for r in out_rows:
            r[7] = int(r[7]) if r[7] == int(r[7]) else r[7]
            w.writerow(r)
    print(f"{OUT.relative_to(ROOT)}: {len(out_rows)} строк")


if __name__ == "__main__":
    main()
