"""Восстанавливает значения с графиков S1 (NF Group, 2025), с. 6–7.

Зачем: ряд ADR / RevPAR / загрузки за 2016–2025 и помесячные данные 2024–2025
есть в S1 только на графиках. Склеивать ряд из таблиц разных выпусков нельзя —
NF Group пересматривает прошлые годы (см. SOURCES.md, «Сверка»). График
в одном отчёте построен по одной методике.

Как:
  1. Графики в PDF векторные: каждый столбец — прямоугольник с точными
     координатами. pdfplumber отдаёт их вместе с цветом заливки.
  2. Калибровка оси: берём подписи оси Y (0, 2 000, 4 000 …) и их координату y,
     подбираем линейную зависимость «значение = a + b·y» методом наименьших
     квадратов. Значение столбца = пересчёт координаты его верхнего края.
  3. Серию (ADR или RevPAR, 2024 или 2025) определяем по цвету, сверяясь с
     легендой графика. Год / месяц — по ближайшей подписи на оси X.
  4. Загрузка: у точек есть подписи (целые проценты) — берём их как есть.
     На помесячном графике подписи двух линий стоят стопкой: верхняя — 2024,
     нижняя — 2025 (проверено по тексту S2 и по среднегодовой загрузке).
  5. Турпоток (с. 6): у всех сегментов есть подписи (млн человек). Подпись
     относим к сегменту столбца (внутренний / внешний), рядом с которым она
     стоит. Первоисточник цифр — Комитет по развитию туризма СПб (S6).
  6. Номерной фонд (с. 3 — гостиницы, с. 4 — апарт-отели): тёмный столбец —
     фонд на начало года (оценка по высоте), красный — ввод за год (подписан,
     берём подпись). Столбец «2026П» = фонд на конец 2025 — по нему проверяем
     калибровку против таблицы S1.
  7. Проверка: восстановленные значения сравниваются с табличными (2024–2025)
     и с цифрами из текста отчётов. Погрешность печатается в консоль.

ВАЖНО: ADR и RevPAR отсюда — оценка по графику (точность ~±1%), не
опубликованная цифра. В анализе помечать как «оценка по графику S1».

Запуск:  .venv/bin/python scripts/extract_nf_charts.py
"""

import csv
import re
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "data" / "raw" / "S1_NF_Group_SPb_hotels_2025.pdf"
CLEAN = ROOT / "data" / "clean"

RED = (0.682, 0.036, 0.194)
DARK = (0.125, 0.188, 0.265)
MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август",
          "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]


def color(obj, key="non_stroking_color"):
    """Цвет заливки (столбцы) или, с key="stroking_color", цвет линии."""
    c = obj.get(key)
    return tuple(round(v, 3) for v in c) if c else None


def fit_axis(words, lines, y_lo, y_hi, x_max=80):
    """Линейная калибровка оси Y.

    Каждую подпись оси ('2 000', '16 000', '0') сопоставляем с ближайшей
    горизонтальной линией сетки: значение относится к линии, а не к центру
    текста (текст стоит чуть выше линии — калибровка по нему даёт +2–3%).
    """
    ticks = {}
    for w in words:
        if w["x1"] <= x_max and y_lo <= w["top"] <= y_hi and re.fullmatch(r"\d+", w["text"]):
            ticks.setdefault(round(w["top"]), []).append(w)
    grid = [l["top"] for l in lines
            if abs(l["top"] - l["bottom"]) < 0.5 and l["x1"] - l["x0"] > 300
            and y_lo - 10 <= l["top"] <= y_hi + 10]
    pts = []
    for ws in ticks.values():
        ws.sort(key=lambda w: w["x0"])
        value = int("".join(w["text"] for w in ws))
        center = (ws[0]["top"] + ws[0]["bottom"]) / 2
        y = min(grid, key=lambda g: abs(g - center))
        if abs(y - center) > 8:
            raise ValueError(f"нет линии сетки у подписи {value}")
        pts.append((y, value))
    n = len(pts)
    my = sum(p[0] for p in pts) / n
    mv = sum(p[1] for p in pts) / n
    b = sum((y - my) * (v - mv) for y, v in pts) / sum((y - my) ** 2 for y, _ in pts)
    a = mv - b * my
    resid = max(abs(a + b * y - v) for y, v in pts)
    return (lambda y: a + b * y), resid, len(pts)


def nearest(x, labels):
    """labels: [(x_center, name)] -> имя ближайшей по x подписи."""
    return min(labels, key=lambda t: abs(t[0] - x))[1]


def merge_numbers(words):
    """Склеивает '1' + '579' -> '1 579', если слова стоят рядом на одной строке."""
    out = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if (out and re.fullmatch(r"\d{1,2}", out[-1]["text"]) and re.fullmatch(r"\d{3}", w["text"])
                and abs(w["top"] - out[-1]["top"]) < 1 and w["x0"] - out[-1]["x1"] < 4):
            prev = out.pop()
            w = dict(w, text=prev["text"] + w["text"], x0=prev["x0"])
        out.append(dict(w))
    return out


def supply_chart(page, y_lo, y_hi):
    """Фонд на начало года (оценка по столбцу) и ввод (подпись) по годам."""
    words, rects, lines = page.extract_words(), page.rects, page.lines
    to_val, resid, _ = fit_axis(words, lines, y_lo, y_hi, x_max=85)
    axis_top = next(w["top"] for w in words if w["text"] == "2016" and y_lo < w["top"] < y_hi + 20)
    # «2026П» — прогноз; суффикс «П» может быть слит с годом
    years = [((w["x0"] + w["x1"]) / 2, int(w["text"][:4])) for w in words
             if re.fullmatch(r"20\d\dП?", w["text"]) and abs(w["top"] - axis_top) < 2]
    zero_y = max(l["top"] for l in lines if y_lo < l["top"] < y_hi + 5 and l["x1"] - l["x0"] > 300)
    res = {y: {} for _, y in years}
    for r in rects:
        if color(r) == DARK and y_lo < r["top"] < y_hi and r["width"] > 8 and r["height"] > 0.5:
            res[nearest((r["x0"] + r["x1"]) / 2, years)]["start_est"] = round(to_val(r["top"]))
    for w in merge_numbers(words):
        if (re.fullmatch(r"\d+", w["text"]) and w["x0"] > 85 and y_lo < w["top"] < zero_y
                and w["top"] < axis_top - 5):
            yr = nearest((w["x0"] + w["x1"]) / 2, years)
            if "intake" in res[yr]:
                raise ValueError(f"ввод {yr}: две подписи")
            res[yr]["intake"] = int(w["text"])
    return res, resid


def main():
    with pdfplumber.open(PDF) as pdf:
        page = pdf.pages[6]
        words = page.extract_words()
        rects, lines = page.rects, page.lines

    # ---------- Годовой график (верхний): 2016–2025 ----------
    Y_TOP, Y_BOT = 330, 500
    to_val, resid, nt = fit_axis(words, lines, Y_TOP, Y_BOT)
    print(f"Годовой график: калибровка по {nt} подписям оси, макс. невязка {resid:.1f} ₽")
    years = [((w["x0"] + w["x1"]) / 2, int(w["text"])) for w in words
             if re.fullmatch(r"20\d\d", w["text"]) and 485 < w["top"] < 495]
    # Легенда: красный квадрат — «Доход на номер (RevPAR)», тёмный — «Средняя стоимость (ADR)»
    series = {RED: "revpar", DARK: "adr"}
    annual = {y: {} for _, y in years}
    for r in rects:
        c = color(r)
        if c in series and Y_TOP < r["top"] < Y_BOT and r["height"] > 7 and r["width"] > 8:
            yr = nearest((r["x0"] + r["x1"]) / 2, years)
            annual[yr][series[c]] = round(to_val(r["top"]))
    occ_labels = [w for w in words if re.fullmatch(r"\d+%", w["text"]) and 355 < w["top"] < 425]
    for w in occ_labels:
        yr = nearest((w["x0"] + w["x1"]) / 2, years)
        annual[yr]["occupancy"] = int(w["text"][:-1])

    # ---------- Помесячный график (нижний): 2024 и 2025 ----------
    M_TOP, M_BOT = 580, 702
    to_val_m, resid_m, nt_m = fit_axis(words, lines, M_TOP, M_BOT)
    print(f"Помесячный график: калибровка по {nt_m} подписям оси, макс. невязка {resid_m:.1f} ₽")
    months = [((w["x0"] + w["x1"]) / 2, MONTHS.index(w["text"]) + 1) for w in words
              if w["text"] in MONTHS and w["top"] > 700]
    # Легенда: тёмный — 2024, красный — 2025 (и для столбцов ADR, и для линий загрузки)
    year_of = {DARK: 2024, RED: 2025}
    monthly = {(y, m): {} for y in (2024, 2025) for _, m in months}
    for r in rects:
        c = color(r)
        if c in year_of and M_TOP < r["top"] < M_BOT and r["height"] > 7 and r["width"] > 8:
            m = nearest((r["x0"] + r["x1"]) / 2, months)
            monthly[(year_of[c], m)]["adr"] = round(to_val_m(r["top"]))
    # Подписи загрузки стоят стопкой под линиями: в каждом месяце две подписи,
    # верхняя относится к 2024, нижняя — к 2025. Проверено: июнь 2025 = 76%,
    # июнь 2024 = 79% (текст S2), средние по подписям совпадают с годовой
    # загрузкой из таблицы S1 (см. проверку ниже).
    by_month = {}
    for w in words:
        if re.fullmatch(r"\d+%", w["text"]) and 585 < w["top"] < 650:
            m = nearest((w["x0"] + w["x1"]) / 2, months)
            by_month.setdefault(m, []).append(w)
    for m, ws in by_month.items():
        if len(ws) != 2:
            raise ValueError(f"месяц {m}: {len(ws)} подписей загрузки, ждали 2")
        upper, lower = sorted(ws, key=lambda w: w["top"])
        monthly[(2024, m)]["occupancy"] = int(upper["text"][:-1])
        monthly[(2025, m)]["occupancy"] = int(lower["text"][:-1])

    # ---------- Турпоток (с. 6): столбцы с накоплением, всё подписано ----------
    with pdfplumber.open(PDF) as pdf:
        p6 = pdf.pages[5]
        w6, r6 = p6.extract_words(), p6.rects
    chart_top = next(w["top"] for w in w6 if w["text"] == "Динамика")
    axis_top = next(w["top"] for w in w6 if w["text"] == "2016" and w["top"] > chart_top)
    years6 = [((w["x0"] + w["x1"]) / 2, int(w["text"])) for w in w6  # только строка оси X
              if re.fullmatch(r"20\d\d", w["text"]) and abs(w["top"] - axis_top) < 2]
    # Легенда: красный — «Внутренний турпоток», тёмный — «Внешний турпоток»
    kind = {RED: "domestic", DARK: "foreign"}
    segs = [r for r in r6 if color(r) in kind and r["top"] > chart_top + 10 and r["width"] > 20]
    flow = {y: {} for _, y in years6}
    for w in w6:
        if not re.fullmatch(r"\d+,\d", w["text"]) or w["top"] < chart_top:
            continue
        x, yc = (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2
        cand = [r for r in segs if r["x0"] <= x <= r["x1"]]
        seg = min(cand, key=lambda r: 0 if r["top"] <= yc <= r["bottom"]
                  else min(abs(yc - r["top"]), abs(yc - r["bottom"])))
        yr = nearest(x, years6)
        k = kind[color(seg)]
        if k in flow[yr]:
            raise ValueError(f"турпоток {yr}: две подписи для {k}")
        flow[yr][k] = float(w["text"].replace(",", "."))

    # ---------- Номерной фонд (с. 3–4) ----------
    with pdfplumber.open(PDF) as pdf:
        hotels, _ = supply_chart(pdf.pages[2], 565, 735)
        apart, _ = supply_chart(pdf.pages[3], 400, 535)

    # ---------- Запись ----------
    with open(CLEAN / "nf_annual_chart.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year", "adr_est", "revpar_est", "occupancy_label", "source"])
        for yr in sorted(annual):
            a = annual[yr]
            w.writerow([yr, a.get("adr"), a.get("revpar"), a.get("occupancy"), "S1 с. 7, график"])
    with open(CLEAN / "nf_monthly_chart.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year", "month", "adr_est", "occupancy_label", "source"])
        for (yr, m) in sorted(monthly):
            d = monthly[(yr, m)]
            w.writerow([yr, m, d.get("adr"), d.get("occupancy"), "S1 с. 7, график"])

    with open(CLEAN / "tourist_flow_chart.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year", "domestic_mln", "foreign_mln", "total_mln", "source"])
        for yr in sorted(flow):
            d = flow[yr]
            w.writerow([yr, d["domestic"], d["foreign"], round(d["domestic"] + d["foreign"], 1),
                        "S1 с. 6, подписи графика; первоисточник — Комитет по развитию туризма"])

    with open(CLEAN / "nf_supply_chart.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year", "segment", "start_rooms_est", "intake_label", "is_forecast", "source"])
        for seg, data, pg in [("hotels", hotels, 3), ("apart", apart, 4)]:
            for yr in sorted(data):
                d = data[yr]
                w.writerow([yr, seg, d.get("start_est", 0), d.get("intake"), int(yr == 2026),
                            f"S1 с. {pg}, график"])

    # ---------- Проверка против опубликованных цифр ----------
    known = [
        ("ADR 2025, таблица S1", annual[2025]["adr"], 8496),
        ("ADR 2024, таблица S1", annual[2024]["adr"], 7614),
        ("RevPAR 2025, таблица S1", annual[2025]["revpar"], 5412),
        ("RevPAR 2024, таблица S1", annual[2024]["revpar"], 4995),
        ("Загрузка 2025, таблица S1 (63,7%)", annual[2025]["occupancy"], 64),
        ("Загрузка 2024, таблица S1 (65,6%)", annual[2024]["occupancy"], 66),
        ("ADR июнь 2025, текст S2 («16 тыс.»)", monthly[(2025, 6)]["adr"], 16000),
        ("Загрузка июнь 2025, текст S2", monthly[(2025, 6)]["occupancy"], 76),
        ("Загрузка июнь 2024, текст S2 (76% + 3 п. п.)", monthly[(2024, 6)]["occupancy"], 79),
    ]
    print("\nПроверка восстановленных значений:")
    for name, got, exp in known:
        err = (got - exp) / exp * 100
        print(f"  {name}: график {got}, опубликовано {exp}, отклонение {err:+.1f}%")
    for seg, data, end24, end25, in24, in25 in [("гостиницы", hotels, 15057, 15770, 321, 802),
                                                ("апарт-отели", apart, 8738, 9132, 803, 491)]:
        for name, got, exp in [(f"фонд {seg} на начало 2025", data[2025]["start_est"], end24),
                               (f"фонд {seg} на начало 2026", data[2026]["start_est"], end25)]:
            print(f"  {name}: график {got}, таблица S1 {exp}, отклонение {(got - exp) / exp * 100:+.1f}%")
        print(f"  ввод {seg} 2024/2025: подписи {data[2024].get('intake')}/{data[2025].get('intake')}, "
              f"таблица S1 {in24}/{in25}")
    for yr, text_total, where in [(2025, 12.4, "S1 с. 6"), (2024, 11.6, "S3 с. 5"),
                                  (2019, 10.3, "S1 с. 6; в S3 — 10,4")]:
        got = flow[yr]["domestic"] + flow[yr]["foreign"]
        print(f"  Турпоток {yr}: сумма по графику {got:.1f} млн, текст {where}: {text_total}")
    for yr, table in [(2024, 65.6), (2025, 63.7)]:
        vals = [monthly[(yr, m)]["occupancy"] for m in range(1, 13)]
        print(f"  Загрузка {yr}: среднее 12 месячных подписей {sum(vals) / 12:.1f}%, "
              f"таблица S1 {table}%")
    missing = [k for k, v in monthly.items() if len(v) < 2] + [k for k, v in annual.items() if len(v) < 3]
    print("Пропуски:", missing or "нет")
    print(f"\nЗаписано: nf_annual_chart.csv ({len(annual)} лет), nf_monthly_chart.csv "
          f"({len(monthly)} мес.), tourist_flow_chart.csv ({len(flow)} лет), nf_supply_chart.csv")


if __name__ == "__main__":
    main()
