"""Извлекает показатели гостиниц из отчётов IBC Real Estate (данные Hotel Advisors и Росстата).

Источники:
  S13 — «Гостиничная недвижимость, II кв. 2026»:
        с. 27 (Петербург) и с. 19 (Москва) — загрузка и средняя цена по ценовым
        сегментам за январь–июнь 2024, 2025, 2026;
        с. 13 — изменение RevPAR за I пол. 2026 по городам и группа, в которую
        IBC отнёс город («снижение», «стабилизация», «замедление роста», «уверенный рост»);
        с. 8 и 32 — число размещённых лиц за январь–май 2026 (Росстат): Россия и топ-20 регионов.
  S10 — «Коммерческая недвижимость Санкт-Петербурга. Предварительные итоги
        I пол. 2026», с. 7: годовой ряд 2023–2025, январь–май 2026, прогноз 2026.

Выборка IBC: сетевые и несетевые классифицированные отели 3–5* от 100 номеров
(~85 отелей, 19,6 тыс. номеров). Апарт-отелей нет. Это НЕ та же выборка,
что у NF Group, — сравнивать можно направление и темпы, а не уровни.

Как:
  1. Вырезает область таблицы на странице (координаты подобраны по PDF)
     и берёт её текст — строки таблицы идут по порядку.
  2. Название строки может быть разбито на две строки текста
     («Верхний предел» / «среднеценового») — склеивает.
  3. В S10 к числам приклеены номера сносок: «56%2» = 56% со сноской 2
     (январь–май), «9,93» = 9,9 со сноской 3 (прогноз). Скрипт отделяет
     сноску: у всех значений в таблице ровно один знак после запятой.
  4. Проверки: RevPAR ≈ ADR × загрузка; рост ADR совпадает с напечатанным.

Запуск:  .venv/bin/python scripts/extract_ibc.py
"""

import csv
import re
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"

NUM = re.compile(r"^(\d+(?:,\d)?%?)(\d?)$")  # значение + необязательная сноска


def parse_value(token):
    m = NUM.match(token)
    if not m:
        raise ValueError(f"не число: {token}")
    return float(m.group(1).rstrip("%").replace(",", ".")), m.group(2)


def table_rows(text):
    """Строки вида 'Название 1 2 3'; название может быть разнесено на строку выше и ниже."""
    rows, pending = [], ""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        parts = lines[i].split()
        nums = [p for p in parts if NUM.match(p)]
        label = " ".join(p for p in parts if not NUM.match(p))
        if nums and all(re.fullmatch(r"20\d\d", n) for n in nums):
            i += 1
            continue  # строка заголовка с годами
        if len(nums) >= 3:
            if label and pending:
                label = f"{pending} {label}"  # «Общее» / «предложение, 18,2 …»
            elif not label:  # «Верхний предел» / числа / «среднеценового»
                label = pending
                if i + 1 < len(lines) and not any(NUM.match(p) for p in lines[i + 1].split()):
                    label = f"{label} {lines[i + 1].strip()}"
                    i += 1
            rows.append((label.strip(), nums))
            pending = ""
        else:
            pending = f"{pending} {label}".strip()
        i += 1
    return rows


S13 = RAW / "S13_IBC_Hotels_Russia_Q2_2026.pdf"


def segments_s13(page_no, city):
    with pdfplumber.open(S13) as pdf:
        page = pdf.pages[page_no - 1]
        assert f"Операционные показатели: {city}" in page.extract_text()
        occ = table_rows(page.crop((440, 230, 690, 495)).extract_text())
        adr = table_rows(page.crop((690, 230, 960, 495)).extract_text())
        head = page.crop((440, 110, 960, 160)).extract_text()

    periods = ["2024-H1", "2025-H1", "2026-H1"]
    out = []
    assert [r[0] for r in occ] == [r[0] for r in adr], "сегменты в двух таблицах не совпали"
    for (seg, occ_vals), (_, adr_vals) in zip(occ, adr):
        for p, o, a in zip(periods, occ_vals, adr_vals):
            out.append({"source_id": "S13", "city": city, "period": p, "segment": seg,
                        "occupancy_pct": parse_value(o)[0], "adr_thousand_rub": parse_value(a)[0]})
    # Заголовок: «6,1 -1% г/г 59 -3 п.п. г/г 10,3 +8% г/г» — RevPAR, загрузка, ADR за 2026
    revpar = float(head.split()[0].replace(",", "."))
    return out, revpar


def annual_s10():
    with pdfplumber.open(RAW / "S10_IBC_SPb_prelim_H1_2026.pdf") as pdf:
        page = pdf.pages[6]
        assert "Гостиничная недвижимость" in page.extract_text()
        rows = table_rows(page.crop((40, 95, 470, 480)).extract_text())

    # Ищем строку по ключевому слову: к названию может прилипнуть единица
    # измерения предыдущей строки («тыс. номеров Новое строительство,»)
    names = {"предложение": "rooms_total", "строительство": "new_rooms",
             "Загрузка": "occupancy", "Средняя цена": "adr", "Выручка": "revpar"}
    units = {"rooms_total": "тыс. номеров", "new_rooms": "тыс. номеров", "occupancy": "%",
             "adr": "тыс. руб.", "revpar": "тыс. руб."}
    # Колонки: 2023, 2024, 2025, «I пол. 2026» (сноска 2 — фактически январь–май), 2026П
    periods = ["2023", "2024", "2025", "2026-H1", "2026"]
    notes = {"2": "январь–май 2026", "3": "прогноз IBC"}
    out = []
    for label, vals in rows:
        key = next(v for k, v in names.items() if k in label)
        for p, token in zip(periods, vals):
            value, fn = parse_value(token)
            note = notes.get(fn, "")
            if p == "2026" and not note:
                note = "прогноз IBC"      # колонка 2026П — прогноз и для строк без сноски
            if p == "2026-H1" and key in ("rooms_total", "new_rooms"):
                note = "на 30.06.2026"
            out.append({"source_id": "S10", "period": p if note != "январь–май 2026" else "2026-01..05",
                        "metric": key, "unit": units[key], "value": value, "note": note})
    return out


def cities_s13():
    """С. 13: четыре группы городов (квадранты), в каждой — «Город (±N%)»."""
    with pdfplumber.open(S13) as pdf:
        page = pdf.pages[12]
        words = page.extract_words()
    groups = {("top", "left"): "снижение RevPAR", ("top", "right"): "стабилизация (±5%)",
              ("bottom", "left"): "замедление роста", ("bottom", "right"): "уверенный рост"}
    # Примеры городов стоят в строках ниже подписи «Примеры локаций:»
    examples = [w for w in words if w["text"] == "Примеры"]
    out = []
    for ex in examples:
        side = "left" if ex["x0"] < 420 else "right"
        half = "top" if ex["top"] < 300 else "bottom"
        x_lo = ex["x0"] - 5
        x_hi = 420 if side == "left" else 680
        area = [w for w in words if x_lo <= w["x0"] < x_hi and ex["top"] + 10 < w["top"] < ex["top"] + 80]
        # внутри квадранта могут быть две колонки; строка = одинаковый top, колонка — по разрыву
        lines = {}
        for w in sorted(area, key=lambda w: (round(w["top"]), w["x0"])):
            lines.setdefault(round(w["top"]), []).append(w)
        for ws in lines.values():
            name = []
            for w in ws:
                t = w["text"]
                m = re.fullmatch(r"\(([+-]\d+)%\)?", t)
                if m:
                    out.append({"source_id": "S13", "location": " ".join(name),
                                "revpar_change_pct": int(m.group(1)),
                                "ibc_group": groups[(half, side)]})
                    name = []
                elif t != ")":
                    name.append(t)
    return out


def placed_s13():
    """С. 32: топ-20 регионов; с. 8: Россия в целом. Январь–май 2026, Росстат."""
    with pdfplumber.open(S13) as pdf:
        w32 = pdf.pages[31].extract_words()
        t8 = pdf.pages[7].extract_text()
    out = []
    for col_x, name_lo, name_hi, val_x in [(191, 300, 470, 490), (579, 690, 860, 879)]:
        ranks = [w for w in w32 if abs(w["x0"] - col_x) < 3 and w["text"].isdigit() and w["top"] > 140]
        for r in ranks:
            same = [w for w in w32 if abs(w["top"] - r["top"]) < 2]
            district = next(w["text"] for w in same if r["x1"] < w["x0"] < name_lo)
            region = " ".join(w["text"] for w in same if name_lo <= w["x0"] < name_hi)
            near = [w for w in w32 if abs(w["x0"] - val_x) < 15]
            value = next(w for w in near if -12 < w["top"] - r["top"] < -2)
            change = next(w for w in near if 2 < w["top"] - r["top"] < 12)
            out.append({"source_id": "S13", "rank": int(r["text"]), "region": region.replace("–", "-"),
                        "federal_district": district,
                        "placed_mln": float(value["text"].replace(",", ".")),
                        "change_pct": int(change["text"].rstrip("%"))})
    m = re.search(r"([\d,]+)\s*\n?\s*Россия \+(\d+)% г/г", t8)
    out.append({"source_id": "S13", "rank": 0, "region": "Россия", "federal_district": "",
                "placed_mln": float(m.group(1).replace(",", ".")), "change_pct": int(m.group(2))})
    return sorted(out, key=lambda r: r["rank"])


def main():
    seg = []
    for page_no, city in [(27, "Санкт-Петербург"), (19, "Москва")]:
        rows, _ = segments_s13(page_no, city)
        seg += rows
    _, revpar_2026 = segments_s13(27, "Санкт-Петербург")
    ann = annual_s10()
    cities = cities_s13()
    placed = placed_s13()
    old = CLEAN / "ibc_spb_h1_segments.csv"
    if old.exists():
        old.unlink()  # заменён файлом ibc_h1_segments.csv (Петербург + Москва)
    for name, rows in [("ibc_h1_segments.csv", seg), ("ibc_spb_annual.csv", ann),
                       ("ibc_city_revpar_h1_2026.csv", cities), ("ibc_placed_persons_2026.csv", placed)]:
        with open(CLEAN / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"data/clean/{name}: {len(rows)} строк")

    # Проверки
    print("\nПроверки:")
    mkt = {r["period"]: r for r in seg
           if r["segment"] == "Рынок в целом" and r["city"] == "Санкт-Петербург"}
    calc = mkt["2026-H1"]["adr_thousand_rub"] * mkt["2026-H1"]["occupancy_pct"] / 100
    print(f"  S13 I пол. 2026: ADR × загрузка = {calc:.2f}, напечатан RevPAR {revpar_2026}")
    g26 = mkt["2026-H1"]["adr_thousand_rub"] / mkt["2025-H1"]["adr_thousand_rub"] - 1
    g25 = mkt["2025-H1"]["adr_thousand_rub"] / mkt["2024-H1"]["adr_thousand_rub"] - 1
    print(f"  S13 рост ADR: I пол. 2026 {g26:+.1%} (в тексте +8%), I пол. 2025 {g25:+.1%} (в тексте +17%)")
    rp25 = mkt["2025-H1"]["adr_thousand_rub"] * mkt["2025-H1"]["occupancy_pct"] / 100
    print(f"  S13 RevPAR I пол. 2025 по таблице = {rp25:.2f} (в СМИ — «6,2 тыс.», см. SOURCES.md)")
    v = {(r["period"], r["metric"]): r["value"] for r in ann}
    for p in ["2023", "2024", "2025", "2026-01..05", "2026"]:
        print(f"  S10 {p}: ADR × загрузка = {v[(p, 'adr')] * v[(p, 'occupancy')] / 100:.2f}, "
              f"RevPAR {v[(p, 'revpar')]}")

    msk = {r["period"]: r for r in seg if r["segment"] == "Рынок в целом" and r["city"] == "Москва"}
    rp = [msk[p]["adr_thousand_rub"] * msk[p]["occupancy_pct"] / 100 for p in ("2025-H1", "2026-H1")]
    print(f"  S13 Москва: RevPAR по таблице {rp[0]:.2f} → {rp[1]:.2f} ({rp[1] / rp[0] - 1:+.1%}), "
          f"в заголовке 7,2 и −9%")
    spb_city = next(c for c in cities if c["location"] == "Санкт-Петербург")
    print(f"  S13 с. 13: Петербург {spb_city['revpar_change_pct']:+d}% (с. 27: −1%), "
          f"группа «{spb_city['ibc_group']}»; всего городов: {len(cities)}")
    print(f"  S13 с. 32: регионов {len(placed) - 1}, Россия {placed[0]['placed_mln']} млн, "
          f"{placed[0]['change_pct']:+d}% (на с. 8: 34,2 млн, +6%)")


if __name__ == "__main__":
    main()
