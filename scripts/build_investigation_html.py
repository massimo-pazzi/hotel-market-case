"""Собирает страницу «ход исследования» report/index.html из report/investigation.md.

Текст — только из Markdown (единственный источник текста). Каждая
инфографика строится из данных проекта: data/clean/ (через те же запросы
DuckDB, что в sql/analysis/) и data/context/ (вручную перенесённые цифры с
источниками). Места для графиков в Markdown отмечены <!-- chart:имя -->.

report/index.html пишется без <html>/<head>/<body> — их добавляет платформа
публикации артефактов; docs/index.html — та же страница целиком, для GitHub Pages.

Запуск:  .venv/bin/python scripts/build_investigation_html.py
"""

import base64
import csv
import re
import io
import subprocess
from pathlib import Path
from statistics import median

import markdown

ROOT = Path(__file__).resolve().parent.parent
MD = ROOT / "report" / "investigation.md"
OUT = ROOT / "report" / "index.html"
DUCKDB = "/opt/homebrew/bin/duckdb"
W = 680


# ======================= данные =======================
def q(sql):
    res = subprocess.run([DUCKDB, "-csv", "-c", ".read sql/setup.sql", "-c", sql],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    return list(csv.DictReader(io.StringIO(res.stdout)))


def sql_file_table(path, header_start):
    """Возвращает таблицу из вывода SQL-файла, начинающуюся с данного заголовка."""
    out = subprocess.run([DUCKDB, "-csv", "-c", ".read sql/setup.sql", "-c", f".read {path}"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    i = next(k for k, l in enumerate(out) if l.startswith(header_start))
    hdr = out[i].split(",")
    rows = []
    for line in out[i + 1:]:
        vals = next(csv.reader([line]))
        if len(vals) != len(hdr) or vals[0] in hdr:
            break
        rows.append(dict(zip(hdr, vals)))
    return rows


def context(case=None):
    rows = list(csv.DictReader(open(ROOT / "data/context/international_cases.csv", encoding="utf-8")))
    return [r for r in rows if case is None or r["case"] == case]


def num(x):
    return float(str(x).strip('"'))


def fmt(x, nd=1, plus=False):
    s = f"{x:+.{nd}f}" if plus else f"{x:.{nd}f}"
    return s.replace(".", ",").replace("-", "−")


def fmt_int(x):
    return f"{x:,.0f}".replace(",", " ")


# ======================= примитивы SVG =======================
def sc(v, lo, hi, a, b):
    return a + (v - lo) / (hi - lo) * (b - a)


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def figure(svg, title, note, height, desc, width=W):
    return (f'<figure class="chart"><figcaption class="chart-title">{title}</figcaption>'
            f'<div class="chart-scroll"><svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(desc)}">{svg}</svg></div>'
            f'<p class="chart-note">{note}</p></figure>')


def legend(items):
    return '<div class="legend">' + "".join(
        f'<span><i class="sw {c}"></i>{esc(t)}</span>' for t, c in items) + "</div>"


def ygrid(lo, hi, step, y_top, y_bot, x0, x1, suf="", nd=0):
    out, v = [], lo
    while v <= hi + 1e-9:
        y = sc(v, lo, hi, y_bot, y_top)
        out.append(f'<line class="{"axis-zero" if abs(v) < 1e-9 else "grid"}" x1="{x0}" x2="{x1}" y1="{y:.1f}" y2="{y:.1f}"/>')
        out.append(f'<text class="tick" x="{x0 - 8}" y="{y + 4:.1f}" text-anchor="end">{fmt(v, nd)}{suf}</text>')
        v += step
    return "".join(out)


def xgrid(lo, hi, step, x0, x1, y_top, y_bot, suf="", nd=0):
    out, v = [], lo
    while v <= hi + 1e-9:
        x = sc(v, lo, hi, x0, x1)
        out.append(f'<line class="{"axis-zero" if abs(v) < 1e-9 else "grid"}" x1="{x:.1f}" x2="{x:.1f}" y1="{y_top}" y2="{y_bot}"/>')
        out.append(f'<text class="tick" x="{x:.1f}" y="{y_bot + 14}" text-anchor="middle">{fmt(v, nd)}{suf}</text>')
        v += step
    return "".join(out)


def line_chart(series, xs, lo, hi, step, suf="", height=290, label_w=150, xlabel=None, bands=(), extra=""):
    """series: [(name, values, cls, end_label)], xs: подписи оси X (годы)."""
    x0, x1, yt, yb = 46, W - label_w, 18, height - 30
    n = len(xs)
    X = lambda i: sc(i, 0, n - 1, x0, x1)
    Y = lambda v: sc(v, lo, hi, yb, yt)
    out = [ygrid(lo, hi, step, yt, yb, x0, x1, suf)]
    for a, b, text in bands:
        out.append(f'<rect class="band" x="{X(a):.1f}" y="{yt}" width="{X(b) - X(a):.1f}" height="{yb - yt}"/>')
        out.append(f'<text class="band-label" x="{(X(a) + X(b)) / 2:.1f}" y="{yt + 12}" text-anchor="middle">{text}</text>')
    for i, xv in enumerate(xs):
        out.append(f'<text class="tick" x="{X(i):.1f}" y="{height - 10}" text-anchor="middle">{xlabel(xv) if xlabel else xv}</text>')
    ends = []
    for name, vals, cls, end_label in series:
        pts = [(X(i), Y(v)) for i, v in enumerate(vals) if v is not None]
        out.append(f'<polyline class="line {cls}" points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}"/>')
        for i, v in enumerate(vals):
            if v is not None:
                out.append(f'<circle class="hit" cx="{X(i):.1f}" cy="{Y(v):.1f}" r="9"><title>{esc(name)}, {xs[i]}: {fmt(v, 1 if abs(v) < 100 else 0)}{suf}</title></circle>')
        last = max(i for i, v in enumerate(vals) if v is not None)
        out.append(f'<circle class="dot {cls}" cx="{X(last):.1f}" cy="{Y(vals[last]):.1f}" r="4.5"/>')
        ends.append([Y(vals[last]), end_label])
    ends.sort()
    for k in range(1, len(ends)):                     # разводим подписи, чтобы не налезали
        if ends[k][0] - ends[k - 1][0] < 14:
            ends[k][0] = ends[k - 1][0] + 14
    for y, text in ends:
        out.append(f'<text class="label" x="{x1 + 10}" y="{y + 4:.1f}">{esc(text)}</text>')
    return "".join(out) + extra


def vbars(values, cats, lo, hi, step, suf="", height=250, cls_fn=lambda v: "s1", top=18, unit=None, band=None):
    x0, x1, yt, yb = 46, W - 16, top, height - 28
    n = len(values)
    bw = (x1 - x0) / n
    out = []
    if band:
        a, b, text = band
        out.append(f'<rect class="band" x="{x0 + a * bw:.1f}" y="{yt}" width="{(b - a) * bw:.1f}" height="{yb - yt}"/>')
        out.append(f'<text class="band-label" x="{x0 + (a + b) / 2 * bw:.1f}" y="{yt + 12}" text-anchor="middle">{text}</text>')
    out.append(ygrid(lo, hi, step, yt, yb, x0, x1, suf))
    zero = sc(0, lo, hi, yb, yt)
    for i, v in enumerate(values):
        y = sc(v, lo, hi, yb, yt)
        t, h = (y, zero - y) if v >= 0 else (zero, y - zero)
        if h < 1.5:
            t, h = zero - 0.75, 1.5
        bx = x0 + i * bw + bw * 0.2
        out.append(f'<rect class="bar {cls_fn(v)}" x="{bx:.1f}" y="{t:.1f}" width="{bw * 0.6:.1f}" height="{h:.1f}" rx="2">'
                   f'<title>{esc(cats[i])}: {fmt(v, 1, plus=True)}{unit or suf}</title></rect>')
        out.append(f'<text class="tick" x="{x0 + i * bw + bw / 2:.1f}" y="{height - 8}" text-anchor="middle">{esc(cats[i])}</text>')
    return "".join(out)


def hbars(rows, lo, hi, step, suf="", label_w=210, row_h=22, top=10, value_fmt=None, show_values=True):
    """rows: [(label, value, cls)] — горизонтальные столбики, подписи слева, значения у конца."""
    x0, x1 = label_w, W - 56
    height = top + len(rows) * row_h + 26
    yb = top + len(rows) * row_h
    out = [xgrid(lo, hi, step, x0, x1, top, yb, suf)]
    zero = sc(0, lo, hi, x0, x1)
    for i, (label, v, cls) in enumerate(rows):
        yc = top + i * row_h + row_h / 2
        x = sc(v, lo, hi, x0, x1)
        a, b = (zero, x) if v >= 0 else (x, zero)
        out.append(f'<text class="rowlabel {"strong" if "hl" in cls else ""}" x="{x0 - 8}" y="{yc + 4:.1f}" text-anchor="end">{esc(label)}</text>')
        out.append(f'<rect class="bar {cls}" x="{a:.1f}" y="{yc - row_h * 0.32:.1f}" width="{max(b - a, 1.5):.1f}" height="{row_h * 0.64:.1f}" rx="2">'
                   f'<title>{esc(label)}: {value_fmt(v) if value_fmt else fmt(v, 1, plus=True) + suf}</title></rect>')
        if show_values:
            text = value_fmt(v) if value_fmt else fmt(v, 1, plus=True) + suf
            if v < 0 and a - x0 < 52:          # не хватает места слева — подпись внутри столбика
                out.append(f'<text class="value-in" x="{a + 5:.1f}" y="{yc + 4:.1f}">{text}</text>')
            else:
                vx, anchor = (b + 6, "start") if v >= 0 else (a - 6, "end")
                out.append(f'<text class="value" x="{vx:.1f}" y="{yc + 4:.1f}" text-anchor="{anchor}">{text}</text>')
    return "".join(out), height


# ======================= графики =======================
def kpi_tiles():
    idx = q("""WITH f AS (SELECT year, SUM(start_rooms_est + intake_label / 2.0) AS rooms
                          FROM supply_chart WHERE is_forecast = 0 GROUP BY year)
               SELECT f.year, f.rooms, t.total_mln FROM f JOIN tourist_flow t USING (year)
               WHERE f.year IN (2019, 2025) ORDER BY f.year""")
    rooms_g = (num(idx[1]["rooms"]) / num(idx[0]["rooms"]) - 1) * 100
    tour_g = (num(idx[1]["total_mln"]) / num(idx[0]["total_mln"]) - 1) * 100
    h2 = q("""SELECT AVG(a.occupancy_label - b.occupancy_label) AS d FROM monthly_chart a
              JOIN monthly_chart b ON b.month = a.month AND b.year = 2024
              WHERE a.year = 2025 AND a.month >= 7""")[0]["d"]
    fc = {r["scenario"].strip('"'): r for r in sql_file_table("sql/analysis/forecast_2027.sql", "scenario,fund_2026")}
    checks = list(csv.DictReader(open(ROOT / "data/clean/nf_checks.csv", encoding="utf-8")))
    bad = sum(1 for c in checks if c["status"] != "ок")
    tiles = [
        (f"+{fmt(rooms_g, 0)}% / +{fmt(tour_g, 0)}%", "номеров и туристов в Петербурге с 2019 года"),
        (f"{fmt(num(h2), 1)} п. п.", "загрузка во II полугодии 2025 года к 2024-му"),
        (f"{fmt(num(fc['базовый']['occ_2027']), 1)}%", "загрузка в 2027 году, базовый сценарий (2025: 63,7%)"),
        (f"{len(checks)}", f"автоматических проверок данных; найдено расхождений: {bad}"),
    ]
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="kpi-v">{v}</div><div class="kpi-l">{l}</div></div>' for v, l in tiles) + "</div>"


def chart_revisions():
    ind = q("""SELECT source_id, period, value FROM indicators
               WHERE metric = 'adr' AND period IN ('2023', '2024') ORDER BY period, source_id""")
    ch = q("SELECT year, adr_est FROM annual_chart WHERE year IN (2023, 2024) ORDER BY year")
    ed = {"S9": ("выпуск за 2023 год", "s3"), "S3": ("выпуск за 2024 год", "s2"), "S1": ("выпуск за 2025 год", "s1")}
    rows = []
    for period in ("2023", "2024"):
        for r in ind:
            if r["period"] == period:
                name, cls = ed[r["source_id"]]
                rows.append((f"{period}: {name}", num(r["value"]), cls))
        if period == "2023":
            rows.append(("2023: выпуск за 2025 год (график)", num(ch[0]["adr_est"]), "s1"))
    order = {"2023: выпуск за 2023 год": 0, "2023: выпуск за 2024 год": 1, "2023: выпуск за 2025 год (график)": 2,
             "2024: выпуск за 2024 год": 3, "2024: выпуск за 2025 год": 4}
    rows.sort(key=lambda r: order.get(r[0], 9))
    svg, h = hbars(rows, 0, 8000, 2000, label_w=250, row_h=26, value_fmt=lambda v: f"{fmt_int(v)} ₽")
    return figure(svg, "Средняя цена номера за один и тот же год в разных выпусках NF Group, ₽",
                  "Таблицы «Основные показатели» выпусков 2023, 2024 и 2025 годов (S9, S3, S1); значение 2023 года "
                  "в выпуске 2025-го — оценка по графику. Разница между выпусками за 2023 год — 15%.",
                  h, "Горизонтальные столбики: цена номера за 2023 и 2024 годы в разных выпусках отчёта")


def chart_calibration():
    log = list(csv.DictReader(open(ROOT / "data/context/chart_calibration_log.csv", encoding="utf-8")))
    now = {}
    a = {r["year"]: r for r in q("SELECT year, adr_est, revpar_est FROM annual_chart WHERE year IN (2024, 2025)")}
    m = q("SELECT adr_est FROM monthly_chart WHERE year = 2025 AND month = 6")[0]
    now["ADR 2025"], now["ADR 2024"] = num(a["2025"]["adr_est"]), num(a["2024"]["adr_est"])
    now["RevPAR 2025"], now["RevPAR 2024"] = num(a["2025"]["revpar_est"]), num(a["2024"]["revpar_est"])
    now["ADR июнь 2025"] = num(m["adr_est"])
    x0, x1, top, rh = 150, W - 40, 12, 30
    lo, hi = -1, 4
    height = top + len(log) * rh + 30
    yb = top + len(log) * rh
    out = [xgrid(lo, hi, 1, x0, x1, top, yb, "%")]
    out.append(f'<rect class="okzone" x="{sc(-1, lo, hi, x0, x1):.1f}" y="{top}" width="{sc(1, lo, hi, x0, x1) - sc(-1, lo, hi, x0, x1):.1f}" height="{yb - top}"/>')
    for i, r in enumerate(log):
        yc = top + i * rh + rh / 2
        e1 = num(r["first_version_error_pct"])
        e2 = (now[r["control_point"]] / num(r["published"]) - 1) * 100
        X1, X2 = sc(e1, lo, hi, x0, x1), sc(e2, lo, hi, x0, x1)
        out.append(f'<text class="rowlabel" x="{x0 - 8}" y="{yc + 4:.1f}" text-anchor="end">{esc(r["control_point"])}</text>')
        out.append(f'<line class="connector" x1="{X2:.1f}" x2="{X1:.1f}" y1="{yc:.1f}" y2="{yc:.1f}"/>')
        out.append(f'<circle class="dot s2" cx="{X1:.1f}" cy="{yc:.1f}" r="5.5"><title>Первая версия: {fmt(e1, 1, True)}%</title></circle>')
        out.append(f'<circle class="dot s1" cx="{X2:.1f}" cy="{yc:.1f}" r="5.5"><title>После исправления: {fmt(e2, 1, True)}%</title></circle>')
    return (legend([("первая версия скрипта", "s2"), ("после исправления", "s1")]) +
            figure("".join(out), "Отклонение восстановленных по графику значений от опубликованных, %",
                   "Контрольные точки — цифры, опубликованные в таблицах и тексте NF Group. Зелёная полоса — "
                   "отклонение до ±1%. Журнал первой версии — data/context/chart_calibration_log.csv.",
                   height, "Точечный график: ошибка восстановления до и после исправления калибровки"))


def chart_supply_demand():
    rows = q("""WITH f AS (SELECT year, SUM(start_rooms_est + intake_label / 2.0) AS rooms
                          FROM supply_chart WHERE is_forecast = 0 GROUP BY year)
               SELECT f.year, f.rooms, t.total_mln FROM f JOIN tourist_flow t USING (year)
               WHERE f.year >= 2016 ORDER BY f.year""")
    b = next(r for r in rows if r["year"] == "2019")
    rooms = [num(r["rooms"]) / num(b["rooms"]) * 100 for r in rows]
    tour = [num(r["total_mln"]) / num(b["total_mln"]) * 100 for r in rows]
    years = [r["year"] for r in rows]
    svg = line_chart([("Номерной фонд", rooms, "s1", f"Номера: {fmt(rooms[-1], 0)}"),
                      ("Турпоток", tour, "s2", f"Туристы: {fmt(tour[-1], 0)}")],
                     years, 0, 180, 30, bands=[(3.5, 5.5, "ковид")])
    return figure(svg, "Номерной фонд и турпоток Петербурга, 2019 = 100",
                  "Средний номерной фонд качественных отелей — оценка по графикам NF Group (S1); турпоток — "
                  "Комитет по развитию туризма в обзоре NF Group.", 290,
                  "Линейный график номерного фонда и турпотока, индекс 2019 = 100")


def chart_revpar_monthly():
    rows = q("""SELECT a.month, (a.adr_est * a.occupancy_label / (b.adr_est * b.occupancy_label) - 1) * 100 AS g
                FROM monthly_chart a JOIN monthly_chart b ON b.month = a.month AND b.year = 2024
                WHERE a.year = 2025 ORDER BY a.month""")
    names = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
    vals = [num(r["g"]) for r in rows]
    svg = vbars(vals, names, -10, 20, 5, "%", height=260, cls_fn=lambda v: "s1" if v >= 0 else "s2",
                band=(6, 12, "II полугодие"))
    return figure(svg, "Доход на номер (RevPAR), 2025 к 2024 году по месяцам",
                  "RevPAR = цена × загрузка; цена — оценка по графику NF Group (S1), загрузка — подписи графика.",
                  260, "Столбчатый график: изменение дохода на номер по месяцам 2025 года")


def chart_check_2026():
    ibc = {r["period"]: r for r in q("""SELECT period, occupancy_pct, adr_thousand_rub FROM ibc_segments
                                        WHERE city = 'Санкт-Петербург' AND segment = 'Рынок в целом'""")}
    g25 = (num(ibc["2025-H1"]["adr_thousand_rub"]) / num(ibc["2024-H1"]["adr_thousand_rub"]) - 1) * 100
    g26 = (num(ibc["2026-H1"]["adr_thousand_rub"]) / num(ibc["2025-H1"]["adr_thousand_rub"]) - 1) * 100
    occ26 = num(ibc["2026-H1"]["occupancy_pct"]) - num(ibc["2025-H1"]["occupancy_pct"])
    ctx = {(r["metric"], r["period"]): num(r["value"]) for r in context("Петербург 2026")}
    rows1 = [("IBC / Hotel Advisors: I пол. 2025", g25, "s2"), ("IBC / Hotel Advisors: I пол. 2026", g26, "s1"),
             ("Vertical Hotels: I пол. 2025", ctx[("Рост цены (Vertical Hotels)", "I пол. 2025")], "s2"),
             ("Vertical Hotels: I пол. 2026", ctx[("Рост цены (Vertical Hotels)", "I пол. 2026")], "s1")]
    s1, h1 = hbars(rows1, 0, 20, 5, "%", label_w=250, row_h=24)
    rows2 = [("IBC / Hotel Advisors, загрузка", occ26, "s2"),
             ("Becar, загрузка", ctx[("Изменение загрузки (Becar)", "I пол. 2026 г/г")], "s2"),
             ("Росстат, число гостей, январь–май", 0.0, "s3")]
    s2, h2 = hbars(rows2, -4, 0, 1, "", label_w=250, row_h=24, value_fmt=lambda v: f"{fmt(v, 0, plus=v != 0)}")
    return (figure(s1, "Рост средней цены номера за полугодие к прошлому году, %",
                   "IBC — данные Hotel Advisors (S13); Vertical Hotels — в пресс-релизе Becar (S11).", h1,
                   "Столбики: рост цены в I полугодии 2025 и 2026 годов по двум источникам") +
            figure(s2, "I полугодие 2026 года к I полугодию 2025-го: загрузка, п. п.; число гостей, %",
                   "IBC (S13), Becar (S11), Росстат в отчёте IBC (S14). Выборки разные — сравнивается направление.",
                   h2, "Столбики: изменение загрузки и числа гостей в 2026 году по трём источникам"))


def chart_cities():
    rows = q("SELECT location, revpar_change_pct FROM ibc_city_revpar ORDER BY revpar_change_pct")
    med = median(num(r["revpar_change_pct"]) for r in rows)
    data = [(r["location"], num(r["revpar_change_pct"]),
             "s1 hl" if r["location"] == "Санкт-Петербург" else ("s2" if r["location"] == "Москва" else "neutral"))
            for r in rows]
    s1, h1 = hbars(data, -30, 25, 10, "%", label_w=170, row_h=17)
    x_med = sc(med, -30, 25, 170, W - 56)
    s1 += (f'<line class="median" x1="{x_med:.1f}" x2="{x_med:.1f}" y1="6" y2="{h1 - 26}"/>'
           f'<text class="band-label" x="{x_med + 4:.1f}" y="{h1 - 30}">медиана {fmt(med, 1)}%</text>')
    pl = q("""SELECT region, change_pct FROM ibc_placed
              WHERE region IN ('Россия','Москва','Московская область','Санкт-Петербург','Республика Татарстан',
                               'Свердловская область','Краснодарский край','Новосибирская область')
              ORDER BY change_pct DESC""")
    data2 = [(r["region"], num(r["change_pct"]),
              "s1 hl" if r["region"] == "Санкт-Петербург" else ("ink" if r["region"] == "Россия" else "neutral"))
             for r in pl]
    s2, h2 = hbars(data2, -10, 30, 10, "%", label_w=170, row_h=22)
    return (figure(s1, "Изменение дохода на номер в I полугодии 2026 года по 26 городам и курортам, %",
                   "Данные Hotel Advisors в отчёте IBC (S13, с. 13). IBC приводит их как примеры групп городов.",
                   h1, "Горизонтальные столбики: изменение RevPAR по городам, Петербург выделен") +
            figure(s2, "Число гостей в средствах размещения, январь–май 2026 года к 2025-му, %",
                   "Росстат в отчёте IBC (S13, с. 8 и 32).", h2,
                   "Горизонтальные столбики: изменение числа гостей по крупным регионам"))


def chart_msk_spb():
    rows = q("""WITH s AS (SELECT city, segment,
                  MAX(CASE WHEN period='2025-H1' THEN occupancy_pct*adr_thousand_rub END) AS r25,
                  MAX(CASE WHEN period='2026-H1' THEN occupancy_pct*adr_thousand_rub END) AS r26,
                  MAX(CASE WHEN period='2025-H1' THEN adr_thousand_rub END) AS a25
                FROM ibc_segments GROUP BY city, segment)
                SELECT segment, MIN(a25) AS a25,
                  MAX(CASE WHEN city='Санкт-Петербург' THEN (r26/r25-1)*100 END) AS spb,
                  MAX(CASE WHEN city='Москва' THEN (r26/r25-1)*100 END) AS msk
                FROM s GROUP BY segment ORDER BY a25""")
    data = []
    for r in rows:
        data.append((f"{r['segment']}: Петербург", num(r["spb"]), "s1"))
        data.append((f"{r['segment']}: Москва", num(r["msk"]), "s2"))
    svg, h = hbars(data, -20, 15, 5, "%", label_w=290, row_h=17)
    return (legend([("Петербург", "s1"), ("Москва", "s2")]) +
            figure(svg, "Доход на номер по ценовым сегментам, I полугодие 2026 года к 2025-му, %",
                   "Данные Hotel Advisors в отчёте IBC (S13, с. 19 и 27); доход на номер = цена × загрузка.",
                   h, "Парные столбики: изменение дохода на номер в Петербурге и Москве по сегментам"))


def chart_wages():
    rows = q("""SELECT a.year, a.adr_est, a.revpar_est, r.wage_ru_hotels_catering AS wage, r.cpi_spb_dec_dec AS cpi
                FROM annual_chart a JOIN rosstat r USING (year) WHERE a.year >= 2019 ORDER BY a.year""")
    b = rows[0]
    cpi, lvl = [], 100.0
    for i, r in enumerate(rows):
        if i > 0:
            lvl *= num(r["cpi"]) / 100
        cpi.append(lvl)
    ser = lambda k: [num(r[k]) / num(b[k]) * 100 for r in rows]
    adr, rev, wage = ser("adr_est"), ser("revpar_est"), ser("wage")
    svg = line_chart([("Зарплата в гостиницах и общепите", wage, "s2", f"Зарплаты: {fmt(wage[-1], 0)}"),
                      ("Цена номера", adr, "s1", f"Цена номера: {fmt(adr[-1], 0)}"),
                      ("Доход на номер", rev, "s3", f"Доход на номер: {fmt(rev[-1], 0)}"),
                      ("Инфляция в Петербурге", cpi, "s4", f"Инфляция: {fmt(cpi[-1], 0)}")],
                     [r["year"] for r in rows], 0, 250, 50, label_w=170)
    return figure(svg, "Цена номера, доход на номер, зарплаты и инфляция, 2019 = 100",
                  "Цена и доход на номер — оценка по графикам NF Group (S1); зарплата — Росстат, по России, "
                  "гостиницы вместе с общепитом (S15); инфляция — Росстат, Петербург, декабрь к декабрю (S17).",
                  290, "Линейный график: индексы цены номера, дохода на номер, зарплат и инфляции")


def chart_fo_shares():
    rows = q("""WITH s AS (SELECT r.region, r.year, r.guests*100.0/ru.guests AS sh FROM regions r
                JOIN regions ru ON ru.year=r.year AND ru.level='страна' WHERE r.level='федеральный округ')
                SELECT region, MAX(sh) FILTER (WHERE year=2025) - MAX(sh) FILTER (WHERE year=2019) AS d
                FROM s GROUP BY region ORDER BY d DESC""")
    data = [(r["region"].replace(" федеральный округ", ""), num(r["d"]), "s1" if num(r["d"]) >= 0 else "s2") for r in rows]
    svg, h = hbars(data, -6, 2, 1, "", label_w=170, row_h=22, value_fmt=lambda v: f"{fmt(v, 1, plus=True)} п. п.")
    return figure(svg, "Изменение доли округа в числе гостей России, 2019 → 2025, п. п.",
                  "Росстат, все средства размещения и все цели поездок (S21).", h,
                  "Горизонтальные столбики: изменение доли федеральных округов в числе гостей")


def chart_tension():
    names = ["г.Москва", "Приморский край", "г.Санкт-Петербург", "Московская область", "Новосибирская область",
             "Свердловская область", "Челябинская область", "Волгоградская область",
             "Тюменская область (кроме Ханты-Мансийского автономного округа-Югры и Ямало-Ненецкого автономного округа)"]
    rows = q(f"""SELECT region, MAX(guests*1.0/rooms) FILTER (WHERE year=2019) AS g19,
                 MAX(guests*1.0/rooms) FILTER (WHERE year=2025) AS g25 FROM regions
                 WHERE region IN ({",".join("'" + n + "'" for n in names)}) GROUP BY region
                 ORDER BY g25/g19""")
    x0, x1, top, rh = 190, W - 60, 10, 24
    lo, hi = 40, 180
    height = top + len(rows) * rh + 30
    yb = top + len(rows) * rh
    out = [xgrid(lo, hi, 20, x0, x1, top, yb)]
    for i, r in enumerate(rows):
        yc = top + i * rh + rh / 2
        a, b = num(r["g19"]), num(r["g25"])
        Xa, Xb = sc(a, lo, hi, x0, x1), sc(b, lo, hi, x0, x1)
        name = r["region"].replace("г.", "").replace(
            " (кроме Ханты-Мансийского автономного округа-Югры и Ямало-Ненецкого автономного округа)", " (без ХМАО и ЯНАО)")
        cls = "s2" if b < a else "s1"
        out.append(f'<text class="rowlabel {"strong" if "Петербург" in name else ""}" x="{x0 - 8}" y="{yc + 4:.1f}" text-anchor="end">{esc(name)}</text>')
        out.append(f'<line class="connector" x1="{Xa:.1f}" x2="{Xb:.1f}" y1="{yc:.1f}" y2="{yc:.1f}"/>')
        out.append(f'<circle class="dot hollow" cx="{Xa:.1f}" cy="{yc:.1f}" r="4.5"><title>{esc(name)}, 2019: {fmt(a, 0)}</title></circle>')
        out.append(f'<circle class="dot {cls}" cx="{Xb:.1f}" cy="{yc:.1f}" r="5.5"><title>{esc(name)}, 2025: {fmt(b, 0)}</title></circle>')
        out.append(f'<text class="value" x="{max(Xa, Xb) + 9:.1f}" y="{yc + 4:.1f}">{fmt((b / a - 1) * 100, 0, plus=True)}%</text>')
    return (legend([("2019", "hollow"), ("2025: гостей на номер больше", "s1"), ("2025: меньше", "s2")]) +
            figure("".join(out), "Гостей в год на один номер, 2019 → 2025",
                   "Росстат: размещённые лица / число номеров, все средства размещения (S21). Растёт — спрос "
                   "обгоняет строительство; падает — номеров становится больше, чем гостей.",
                   height, "Гантели: гостей на номер в 2019 и 2025 годах по регионам"))


def chart_lost():
    rows = q("""SELECT a.month, 150 * DAY(LAST_DAY(MAKE_DATE(2025, a.month, 1)))
                       * (b.occupancy_label - a.occupancy_label) / 100.0 * a.adr_est / 1e6 AS lost
                FROM monthly_chart a JOIN monthly_chart b ON b.month = a.month AND b.year = 2024
                WHERE a.year = 2025 ORDER BY a.month""")
    names = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
    vals = [num(r["lost"]) for r in rows]
    svg = vbars(vals, names, 0, 3, 0.5, "", height=240, cls_fn=lambda v: "s2", unit=" млн ₽")
    total = sum(vals)
    warm = sum(vals[3:10])
    return figure(svg, "Упущенная выручка в 2025 году из-за потери загрузки к 2024-му, млн ₽ на отель в 150 номеров",
                  f"Всего {fmt(total, 1)} млн ₽, из них {fmt(warm, 1)} млн — апрель–октябрь. Потерянные номеро-ночи "
                  "оценены по цене 2025 года (NF Group, S1).", 240,
                  "Столбики: упущенная выручка по месяцам 2025 года")


def chart_seasons():
    rows = q("""SELECT a.month, (a.adr_est / b.adr_est - 1) * 100 AS adr, a.occupancy_label - b.occupancy_label AS occ
                FROM monthly_chart a JOIN monthly_chart b ON b.month = a.month AND b.year = 2024
                WHERE a.year = 2025 ORDER BY a.month""")
    names = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
    top = vbars([num(r["adr"]) for r in rows], names, 0, 20, 5, "%", height=200, cls_fn=lambda v: "s1",
                band=(0, 4, "цену подняли, гости остались"))
    bot = vbars([num(r["occ"]) for r in rows], names, -8, 0, 2, "", height=200, cls_fn=lambda v: "s2", unit=" п. п.")
    return (figure(top, "Цена номера, 2025 к 2024 году, %", "", 200, "Столбики: рост цены по месяцам") +
            figure(bot, "Загрузка, 2025 к 2024 году, п. п.",
                   "NF Group (S1): цена — оценка по графику, загрузка — подписи графика (целые проценты).", 200,
                   "Столбики: изменение загрузки по месяцам"))


def chart_economy():
    seg = {r["period"]: r for r in q("""SELECT period, occupancy_pct, adr_thousand_rub FROM ibc_segments
                                        WHERE city='Санкт-Петербург' AND segment='Экономичный'""")}
    o25, a25 = num(seg["2025-H1"]["occupancy_pct"]), num(seg["2025-H1"]["adr_thousand_rub"])
    o26, a26 = num(seg["2026-H1"]["occupancy_pct"]), num(seg["2026-H1"]["adr_thousand_rub"])
    import math
    e = math.log(o26 / o25) / math.log(a26 / a25)
    o4 = o25 * (1.04 ** e)
    rp = lambda o, a: o / 100 * a * 1000
    cards = [("Факт, I пол. 2026", f"+{fmt((a26 / a25 - 1) * 100, 0)}%", f"{fmt(o26, 0)}%", f"{fmt_int(rp(o26, a26))} ₽", "100"),
             ("Если бы цену подняли на 4%", "+4%", f"{fmt(o4, 1)}%", f"{fmt_int(rp(o4, a25 * 1.04))} ₽", fmt(o4 / o26 * 100, 0))]
    html = '<div class="compare">' + "".join(
        f'<div class="cmp"><div class="cmp-h">{h}</div><dl><dt>Рост цены</dt><dd>{p}</dd><dt>Загрузка</dt><dd>{o}</dd>'
        f'<dt>Доход на номер</dt><dd>{r}</dd><dt>Гостей, факт = 100</dt><dd>{g}</dd></dl></div>'
        for h, p, o, r, g in cards) + "</div>"
    return (f'<figure class="chart"><figcaption class="chart-title">Экономичные отели Петербурга: тот же доход — '
            f'больше гостей</figcaption>{html}<p class="chart-note">IBC (S13): I пол. 2025 — загрузка {fmt(o25, 0)}%, '
            f'цена {fmt(a25, 1)} тыс. ₽. Наблюдаемая чувствительность загрузки к цене — {fmt(e, 2)} '
            f'(1% цены ≈ 1% гостей); вариант «+4%» рассчитан по ней.</p></figure>')


def chart_uae():
    rows = context("ОАЭ 2026")
    seq = [("январь–февраль 2026", "янв–фев"), ("неделя до 14.03.2026", "сер. марта"), ("март 2026", "март"),
           ("июнь 2026", "июнь"), ("август 2026", "август")]
    occ = {r["period"]: r for r in rows if r["metric"] == "Загрузка отелей Дубая"}
    vals = [num(occ[p]["value"]) for p, _ in seq]
    det = next(r for r in rows if r["metric"].startswith("Заявление DET"))
    x0, x1, yt, yb, H = 46, W - 150, 18, 240, 270
    X = lambda i: sc(i, 0, len(seq) - 1, x0, x1)
    Y = lambda v: sc(v, 0, 100, yb, yt)
    out = [ygrid(0, 100, 20, yt, yb, x0, x1, "%")]
    out.append(f'<polyline class="line s1" points="{" ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals))}"/>')
    for i, (p, short) in enumerate(seq):
        r = occ[p]
        cls = "s1" if r["independent"] == "да" else "s1 open"
        out.append(f'<circle class="dot {cls}" cx="{X(i):.1f}" cy="{Y(vals[i]):.1f}" r="5"><title>{esc(p)}: {fmt(vals[i], 1)}% — {esc(r["source"].split(" http")[0])}</title></circle>')
        out.append(f'<text class="value" x="{X(i):.1f}" y="{Y(vals[i]) - 10:.1f}" text-anchor="middle">{fmt(vals[i], 0 if vals[i] == int(vals[i]) else 1)}%</text>')
        out.append(f'<text class="tick" x="{X(i):.1f}" y="{H - 10}" text-anchor="middle">{short}</text>')
    dx = X(3)
    out.append(f'<circle class="dot hollow warn" cx="{dx:.1f}" cy="{Y(num(det["value"])):.1f}" r="5"><title>Заявление DET о праздниках, июнь: 77%</title></circle>')
    out.append(f'<text class="label" x="{dx - 10:.1f}" y="{Y(num(det["value"])) + 4:.1f}" text-anchor="end">заявление DET о праздниках: 77%</text>')
    out.append(f'<line class="median" x1="{dx:.1f}" x2="{dx:.1f}" y1="{Y(num(det["value"])) + 6:.1f}" y2="{Y(vals[3]) - 16:.1f}"/>')
    d19 = context("Дубай 2019")
    data = [(r["metric"], num(r["value"]), "s1" if num(r["value"]) >= 0 else "s2") for r in d19]
    s2, h2 = hbars(data, -20, 10, 5, "%", label_w=240, row_h=24)
    return (figure("".join(out), "Загрузка отелей Дубая в 2026 году",
                   "HVS/CoStar, JLL (сплошные точки — независимые данные), DET — туристический департамент Дубая "
                   "(полые точки). Пассажиропоток аэропорта в I полугодии −31%. Источники — data/context/.",
                   H, "Линейный график загрузки отелей Дубая в 2026 году") +
            figure(s2, "Дубай, январь 2019 года к январю 2018-го: избыток номеров", "STR в пересказе HTrends.",
                   h2, "Столбики: предложение, спрос, цена и доход на номер в Дубае"))


def chart_stress():
    rows = sql_file_table("sql/analysis/forecast_2027.sql", "variant,demand_2027_pct")
    v = {r["variant"].strip('"'): num(r["revpar_2027_pct"]) for r in rows}
    steps = [(("Базовый", "сценарий"), v["базовый"], "total"),
             (("Топливо:", "автопоездок −10%"), v["стресс: топливо"] - v["базовый"], "delta"),
             (("Командировки", "−10%"), v["стресс: топливо + бизнес"] - v["стресс: топливо"], "delta"),
             (("Турналог 3%", "за счёт отеля"), v["стресс: всё + налог"] - v["стресс: топливо + бизнес"], "delta"),
             (("Итог", "стресс-варианта"), v["стресс: всё + налог"], "total")]
    x0, x1, yt, yb, H = 46, W - 16, 22, 230, 300
    lo, hi = -1, 5
    n = len(steps)
    bw = (x1 - x0) / n
    Y = lambda val: sc(val, lo, hi, yb, yt)
    out = [ygrid(lo, hi, 1, yt, yb, x0, x1, "%")]
    run = 0.0
    for i, (name, val, kind) in enumerate(steps):
        if kind == "total":
            a, b, cls = 0, val, "s1"
            run = val
        else:
            a, b, cls = run, run + val, "s2"
            run += val
        t, bt = Y(max(a, b)), Y(min(a, b))
        bx = x0 + i * bw + bw * 0.2
        out.append(f'<rect class="bar {cls}" x="{bx:.1f}" y="{t:.1f}" width="{bw * 0.6:.1f}" height="{max(bt - t, 1.5):.1f}" rx="2"><title>{esc(" ".join(name))}: {fmt(val, 1, True)}</title></rect>')
        lab = fmt(val, 1, plus=True) + ("%" if kind == "total" else " п. п.")
        out.append(f'<text class="value" x="{bx + bw * 0.3:.1f}" y="{t - 6:.1f}" text-anchor="middle">{lab}</text>')
        line1, line2 = name
        out.append(f'<text class="tick" x="{bx + bw * 0.3:.1f}" y="{yb + 18}" text-anchor="middle">{esc(line1)}</text>')
        out.append(f'<text class="tick" x="{bx + bw * 0.3:.1f}" y="{yb + 32}" text-anchor="middle">{esc(line2)}</text>')
    return figure("".join(out), "Рост дохода на номер в 2027 году: базовый сценарий и стресс-вариант, %",
                  f"Расчёт — sql/analysis/forecast_2027.sql. Если деловые гости составляют не 11%, а 20% спроса "
                  f"отелей, итог — {fmt(v['стресс: всё + налог, доля бизнеса 20%'], 1, True)}%. Допущения о −10% — "
                  "сценарные, не прогноз.", H, "Каскадная диаграмма: что съедает рост дохода на номер в 2027 году")


def chart_forecast():
    hist = q("SELECT year, occupancy_label AS occ FROM annual_chart ORDER BY year")
    fc = {r["scenario"].strip('"'): r for r in sql_file_table("sql/analysis/forecast_2027.sql", "scenario,fund_2026")}
    years = [r["year"] for r in hist] + ["2026", "2027"]
    actual = [num(r["occ"]) for r in hist] + [None, None]
    actual[-3] = 63.7
    ser = [("Факт", actual, "actual", "Факт 2025: 63,7%")]
    for name, cls in [("хороший", "s3"), ("базовый", "s1"), ("плохой", "s2")]:
        vals = [None] * (len(years) - 3) + [63.7, num(fc[name]["occ_2026"]), num(fc[name]["occ_2027"])]
        ser.append((f"Сценарий «{name}»", vals, f"{cls} dashed", f"{name.capitalize()}: {fmt(vals[-1], 1)}%"))
    svg = line_chart(ser, years, 30, 80, 10, "%", label_w=150, xlabel=lambda y: y if y in ("2016", "2025", "2027") else y[2:],
                     bands=[(len(years) - 3, len(years) - 1, "прогноз")])
    return figure(svg, "Загрузка качественных отелей Петербурга: факт и сценарии, %",
                  "Факт — подписи графика NF Group (S1), 2025 — 63,7% по таблице. Сценарии — "
                  "sql/analysis/forecast_2027.sql.", 290, "Линейный график загрузки: факт и три сценария")


def table(head, rows, cls="actions"):
    return (f'<div class="table-wrap"><table class="{cls}"><thead><tr>' + "".join(f"<th>{h}</th>" for h in head) +
            "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) +
            "</tbody></table></div>")


def chart_actions():
    return table(["Что делать", "На чём основано", "Размер"], [
        ["Планировать бюджет 2027 года на загрузку около 60%", "Шаг 15", "−4 п. п. к 2025 году"],
        ["Поднимать цену в январе–апреле, где гость к ней нечувствителен", "Шаг 11", "≈ 2,7 млн ₽ в год на 150 номеров (0,9% выручки)"],
        ["Беречь гостя летом и осенью и возвращать потерянных в 2025 году", "Шаги 10–11", "до 12,5 млн ₽ (4,3% выручки)"],
        ["Не входить в ценовую войну: пакеты вместо скидок", "Шаги 7, 13", "Москва −9%, Дубай 2019 −16% дохода на номер"],
        ["В экономсегменте — меньше рост цены, больше гостей", "Шаг 12", "+13% гостей при том же доходе на номер"],
        ["Держать штат и затраты под загрузку", "Шаг 8", "зарплаты +24% против дохода на номер +8% в 2025 году"],
        ["Следить за доступностью: Пулково, топливо, дроны", "Шаги 13–14", "стресс-вариант съедает весь рост 2027 года"],
    ])


def chart_mistakes():
    return table(["Ошибка", "Как поймал", "Что сделал"], [
        ["Восстановленные по графику значения завышены на 2–4%", "Сверка с опубликованными цифрами", "Калибровка по линиям сетки, отклонение ≤1% (шаг 2)"],
        ["Фраза «рынок близок к насыщению» приписана Петербургу", "Повторное чтение вёрстки PDF", "Цитата убрана (шаг 6)"],
        ["«Недооценённые» месяцы почти все из 2024 года", "Подозрительный результат", "Цена сравнивается со средней ценой своего года (шаг 11)"],
        ["«Петербург — единственный крупный регион без роста гостей»", "Проверка формулировки по таблице", "В Краснодарском крае −4%; формулировка исправлена"],
        ["Число горничных в отчёте — результат модели на допущениях", "Сам себе возразил: «не смогу защитить»", "Из выводов убрано, оставлено соотношение загрузки"],
        ["Туристический налог «возможно, не платят квартиры»", "Сам себе возразил: это допущение", "Проверено по НК РФ: платят только объекты из реестра (шаг 14)"],
        ["«Главный резерв — загрузить зиму»", "Сам себе возразил: это общее место", "Найдено, где гостей потеряли на самом деле (шаг 10)"],
    ], cls="mistakes")


def chart_quality():
    n_sources = sum(1 for l in open(ROOT / "data/SOURCES.md", encoding="utf-8") if l.startswith("| S"))
    n_raw = len(list((ROOT / "data/raw").glob("S*")))
    n_clean = len(list((ROOT / "data/clean").glob("*.csv")))
    n_scripts = len([p for p in (ROOT / "scripts").glob("*.py") if not p.name.startswith("build_")])
    n_sql = len(list((ROOT / "sql/analysis").glob("*.sql")))
    checks = list(csv.DictReader(open(ROOT / "data/clean/nf_checks.csv", encoding="utf-8")))
    tiles = [(n_sources, "источников в реестре, у каждого — ссылка и статус проверки"),
             (n_raw, "исходных файлов: PDF NF Group и IBC, таблицы Росстата"),
             (n_scripts, "скриптов: загрузка с проверкой сумм, извлечение таблиц и графиков из PDF и Excel, сверка"),
             (n_clean, "чистых таблиц, каждая получена скриптом"),
             (len(checks), "автоматических проверок: суммы, RevPAR = цена × загрузка, сверка выпусков"),
             (n_sql, "SQL-файлов анализа, на которых построены выводы")]
    tiles_html = ('<div class="kpis six">' + "".join(
        f'<div class="kpi"><div class="kpi-v">{v}</div><div class="kpi-l">{l}</div></div>' for v, l in tiles) + "</div>")
    # Что нашли проверки: расхождения сгруппированы по смыслу, а не по технической группе
    bad = [c for c in checks if c["status"] != "ок"]
    revised = [c for c in bad if "пересмотрено" in c["note"]]
    balance = [c for c in bad if "ввод 2025 vs" in c["check"]]
    lists = [c for c in bad if c["group"].startswith("D")]
    typos = [c for c in bad if c["group"].startswith("B")]
    assert len(revised) + len(balance) + len(lists) + len(typos) == len(bad), "неучтённое расхождение"
    adr23 = next(c for c in revised if c["check"].startswith("2023 adr"))
    adr24 = next(c for c in revised if c["check"].startswith("2024 adr"))
    bal = next(c for c in balance if "rooms_total" in c["check"])
    rows = [
        ("NF Group переписывает прошлые годы в следующем выпуске. Цена номера за 2023 год: "
         f"{fmt_int(num(adr23['expected']))} ₽ в выпуске за 2023-й и {fmt_int(num(adr23['actual']))} ₽ в выпуске за 2024-й; "
         f"за 2024 год: {fmt_int(num(adr24['expected']))} → {fmt_int(num(adr24['actual']))} ₽",
         len(revised), "Динамику считаю только по парам лет из одного выпуска; ряд 2016–2025 — из одного графика S1"),
        (f"Фонд на конец 2025 года на {fmt_int(-num(bal['diff']))} номеров меньше, чем «конец 2024 + ввод 2025»: "
         "89 — закрытый «Талион Империал Отель», остальное в отчёте не объяснено",
         len(balance), "Выбытие номеров в обзорах не показывают: чистый прирост фонда меньше объявленного ввода"),
        ("Списки открытых апарт-отелей неполные: в 2025 году по списку 469 номеров из 491, в 2024-м — 7 объектов из 13",
         len(lists), "Ввод беру из сводной таблицы, а не суммой по спискам"),
        ("Опечатка в динамике ввода за I полугодие 2025 года: −76,6% вместо −78,6%",
         len(typos), "На выводы не влияет"),
    ]
    found = ('<div class="table-wrap"><table class="found"><thead><tr><th>Что нашёл</th><th>Проверок</th>'
             '<th>Как учёл в анализе</th></tr></thead><tbody>' +
             "".join(f"<tr><td>{esc(a)}</td><td>{n}</td><td>{esc(b)}</td></tr>" for a, n, b in rows) +
             "</tbody></table></div>"
             f'<p class="chart-note">Остальные {len(checks) - len(bad)} проверок сошлись: суммы частей, '
             'доход на номер = цена × загрузка, цифры из поисковой выдачи = PDF.</p>')
    return tiles_html + found


# Источники, на которые опирается страница. Названия — короткие, ссылки берутся из
# data/SOURCES.md; файлы, которые лежат в репозитории (таблицы Росстата), — ссылкой на файл.
REPO = "https://github.com/massimo-pazzi/hotel-market-case"
SOURCE_TITLES = [
    ("S1", "NF Group, «Рынок гостиничной недвижимости Санкт-Петербурга», 2025 год"),
    ("S2", "NF Group, то же, I полугодие 2025 года"),
    ("S3", "NF Group, то же, 2024 год"),
    ("S9", "NF Group, то же, 2023 год"),
    ("S10", "IBC Real Estate, «Коммерческая недвижимость Санкт-Петербурга. Предварительные итоги I полугодия 2026» (данные Hotel Advisors)"),
    ("S13", "IBC Real Estate, «Гостиничная недвижимость, II квартал 2026» (данные Hotel Advisors и Росстата)"),
    ("S14", "IBC Real Estate, «Коммерческая недвижимость Санкт-Петербурга, II квартал 2026»"),
    ("S11", "Becar Asset Management, итоги I полугодия 2026 года, пресс-релиз"),
    ("S15", "Росстат, средняя зарплата по видам экономической деятельности, 2017–2025"),
    ("S16", "Росстат, средняя зарплата по субъектам РФ"),
    ("S17", "Росстат, индексы потребительских цен по субъектам РФ, 1992–2025"),
    ("S21", "Росстат, средства размещения: номера и размещённые лица по субъектам РФ, 2002–2025"),
    ("S18", "ФНС, «Туристический налог» (Санкт-Петербург)"),
]
CONTEXT_SOURCES = ["Дубай, избыток номеров 2017–2019", "ОАЭ, война с Ираном 2026 г.", "ОАЭ, меры поддержки 2026 г."]


def md_links(cell):
    return re.findall(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", cell)


def chart_sources():
    reg = {}
    context = {}
    for line in open(ROOT / "data/SOURCES.md", encoding="utf-8"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if re.fullmatch(r"S\d+", cells[0]) and len(cells) > 2:
            reg[cells[0]] = cells[1]
        elif cells[0] in CONTEXT_SOURCES:
            context[cells[0]] = cells[-1]
    manifest = {r["source_id"]: r for r in csv.DictReader(open(ROOT / "data/raw_manifest.csv", encoding="utf-8"))}
    items = []
    for sid, title in SOURCE_TITLES:
        m = manifest.get(sid)
        if m and m["in_repo"] == "да":
            links = [("файл в репозитории", f"{REPO}/blob/main/data/raw/{m['file']}")]
        else:
            links = md_links(reg[sid])
            assert links, f"нет ссылки у {sid}"
        a = ", ".join(f'<a href="{u}" target="_blank" rel="noopener">{esc(t)}</a>' for t, u in links)
        items.append(f"<li><span class=\"sid\">{sid}</span> {esc(title)} — {a}</li>")
    ctx = []
    for name in CONTEXT_SOURCES:
        a = ", ".join(f'<a href="{u}" target="_blank" rel="noopener">{esc(t)}</a>' for t, u in md_links(context[name]))
        ctx.append(f"<li>{esc(name)} — {a}</li>")
    rg = re.search(r"\[[^\]]+\]\((https://rg\.ru/[^)]+)\)", open(ROOT / "data/SOURCES.md", encoding="utf-8").read()).group(1)
    return (f'<p class="sources-h">Повод для исследования:</p><ul class="sources"><li>«Российская газета», 29.09.2026, '
            f'«После бурного роста турпоток в Петербург перестал увеличиваться» — '
            f'<a href="{rg}" target="_blank" rel="noopener">rg.ru</a></li></ul>'
            '<p class="sources-h">Данные:</p>'
            '<ol class="sources">' + "".join(items) + "</ol>"
            '<p class="sources-h">Опыт других рынков (шаг 13), только для сравнения:</p>'
            '<ul class="sources">' + "".join(ctx) + "</ul>"
            f'<p>Полный реестр — что взято из каждого источника, статус проверки и ограничения: '
            f'<a href="{REPO}/blob/main/data/SOURCES.md" target="_blank" rel="noopener">data/SOURCES.md</a>.</p>')


def author_block():
    img = base64.b64encode((ROOT / "docs/img/author.jpg").read_bytes()).decode()
    return (f'<div class="author"><img src="data:image/jpeg;base64,{img}" alt="Максим Поципух" width="64" height="64">'
            '<span>Максим Поципух</span></div>')


CSS = """
:root{
  --bg:#f5f6f7; --surface:#ffffff; --ink:#18202a; --ink-2:#4b5662; --muted:#6c7782;
  --rule:#d9dee3; --accent:#93560f; --accent-soft:#f3eadf; --neutral:#aab2bb;
  --series-1:#2a78d6; --series-2:#eb6834; --series-3:#1baf7a; --series-4:#a07800;
  --band:rgba(24,32,42,.045); --ok:rgba(27,175,122,.12);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){ color-scheme:dark;
    --bg:#11161c; --surface:#171d24; --ink:#e7ebef; --ink-2:#b5bec7; --muted:#8c96a0;
    --rule:#2c343d; --accent:#e2a75b; --accent-soft:#2a2219; --neutral:#5d6670;
    --series-1:#3987e5; --series-2:#d95926; --series-3:#199e70; --series-4:#c98500;
    --band:rgba(231,235,239,.05); --ok:rgba(25,158,112,.16); }
}
:root[data-theme="dark"]{ color-scheme:dark;
  --bg:#11161c; --surface:#171d24; --ink:#e7ebef; --ink-2:#b5bec7; --muted:#8c96a0;
  --rule:#2c343d; --accent:#e2a75b; --accent-soft:#2a2219; --neutral:#5d6670;
  --series-1:#3987e5; --series-2:#d95926; --series-3:#199e70; --series-4:#c98500;
  --band:rgba(231,235,239,.05); --ok:rgba(25,158,112,.16); }
body{background:var(--bg); color:var(--ink); font-family:"Golos Text",system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:17px; line-height:1.62; padding-inline:16px; padding-block:40px 64px;}
.page{max-width:46rem; margin:0 auto;}
.eyebrow{font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:12.5px; letter-spacing:.06em; text-transform:uppercase; color:var(--accent); margin:0 0 14px;}
h1{font-size:clamp(1.7rem,4.2vw,2.3rem); line-height:1.18; font-weight:700; letter-spacing:-.01em; text-wrap:balance; margin:0 0 16px;}
h2{font-size:1.28rem; line-height:1.3; font-weight:650; text-wrap:balance; margin:46px 0 12px; padding-top:22px; border-top:1px solid var(--rule);}
h1 + p em,.author + p em{color:var(--ink-2); font-size:15px;} .author + p a,p a{color:var(--accent);}
.author{display:flex; align-items:center; gap:12px; margin:4px 0 16px; font-weight:600; font-size:15px;}
.author img{width:64px; height:64px; border-radius:50%; object-fit:cover; border:1px solid var(--rule);}
.sources{font-size:14.5px; line-height:1.55; padding-left:1.5em;} .sources li{margin-bottom:6px;}
.sources a{color:var(--accent); word-break:break-word;} .sid{font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:12px; color:var(--muted); margin-right:4px;}
.sources-h{margin:14px 0 6px; font-weight:600; font-size:14.5px;}
ol.sources{list-style:none; padding-left:0;}
table.found td:nth-child(2){font-variant-numeric:tabular-nums; text-align:center;}
p{margin:0 0 14px;} strong{font-weight:620;} hr{display:none;}
ol,ul{margin:0 0 14px; padding-left:1.3em;}
code{font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.86em; background:var(--accent-soft); padding:1px 5px; border-radius:3px;}
.kpis{display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin:22px 0 8px;}
.kpi{background:var(--surface); border:1px solid var(--rule); border-radius:6px; padding:14px 14px 12px;}
.kpi-v{font-size:1.45rem; font-weight:700; font-variant-numeric:tabular-nums; letter-spacing:-.01em; color:var(--ink);}
.kpi-l{font-size:13px; line-height:1.4; color:var(--ink-2); margin-top:4px;}
.chart{margin:16px 0 20px; background:var(--surface); border:1px solid var(--rule); border-radius:6px; padding:14px 16px 10px;}
.chart-title{font-weight:600; font-size:14.5px; margin-bottom:6px; line-height:1.4;}
.chart-scroll{overflow-x:auto;} .chart svg{display:block; width:100%; min-width:520px; height:auto;}
.chart-note{font-size:12.5px; color:var(--muted); margin:6px 0 0; line-height:1.5;} .chart-note:empty{display:none;}
.legend{display:flex; flex-wrap:wrap; gap:6px 16px; font-size:13px; color:var(--ink-2); margin:12px 0 -8px;}
.legend span{display:inline-flex; align-items:center; gap:6px;}
.sw{display:inline-block; width:11px; height:11px; border-radius:2px;}
.sw.s1{background:var(--series-1);} .sw.s2{background:var(--series-2);} .sw.hollow{border:2px solid var(--ink-2); border-radius:50%; width:9px; height:9px;}
.grid{stroke:var(--rule); stroke-width:1;} .axis-zero{stroke:var(--ink-2); stroke-width:1;}
.tick{fill:var(--muted); font-size:11px; font-family:"IBM Plex Mono",ui-monospace,monospace;}
.label{fill:var(--ink); font-size:12.5px; font-weight:500;} .value{fill:var(--ink-2); font-size:11.5px; font-variant-numeric:tabular-nums;}
.rowlabel{fill:var(--ink-2); font-size:12px;} .value-in{fill:#fff; font-size:11.5px; font-weight:600;} .rowlabel.strong{fill:var(--ink); font-weight:650;}
.band{fill:var(--band);} .band-label{fill:var(--muted); font-size:10.5px; font-family:"IBM Plex Mono",ui-monospace,monospace;}
.okzone{fill:var(--ok);} .median{stroke:var(--ink-2); stroke-width:1; stroke-dasharray:3 3;}
.connector{stroke:var(--neutral); stroke-width:2;}
.line{fill:none; stroke-width:2.2; stroke-linejoin:round; stroke-linecap:round;} .line.dashed{stroke-dasharray:5 4;}
.line.actual{stroke:var(--ink-2);} .dot.actual{fill:var(--ink-2);}
.s1{stroke:var(--series-1);} .s2{stroke:var(--series-2);} .s3{stroke:var(--series-3);} .s4{stroke:var(--series-4);}
.dot{stroke:var(--surface); stroke-width:2;}
.dot.s1,.bar.s1{fill:var(--series-1);} .dot.s2,.bar.s2{fill:var(--series-2);} .dot.s3,.bar.s3{fill:var(--series-3);} .dot.s4{fill:var(--series-4);}
.bar.neutral{fill:var(--neutral);} .bar.ink{fill:var(--ink-2);}
.dot.hollow{fill:var(--surface); stroke:var(--ink-2); stroke-width:2;} .dot.open{fill:var(--surface); stroke:var(--series-1); stroke-width:2.2;}
.dot.warn{stroke:var(--series-2);}
.bar{stroke:none;} .hit{fill:transparent; stroke:none;} .bar:hover,.dot:hover{opacity:.75;}
.compare{display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px;}
.cmp{border:1px solid var(--rule); border-radius:6px; padding:12px 14px;}
.cmp-h{font-weight:600; font-size:14px; margin-bottom:6px;}
.cmp dl{display:grid; grid-template-columns:1fr auto; gap:4px 12px; margin:0; font-size:14px;}
.cmp dt{color:var(--ink-2);} .cmp dd{margin:0; font-weight:600; font-variant-numeric:tabular-nums; text-align:right;}
.table-wrap{overflow-x:auto; margin:8px 0 18px;}
table{border-collapse:collapse; width:100%; font-size:14.5px;}
th,td{text-align:left; padding:9px 12px 9px 0; border-bottom:1px solid var(--rule); vertical-align:top;}
th{font-weight:600; color:var(--ink-2); font-size:13px;}
table.actions td:last-child{font-weight:600; font-variant-numeric:tabular-nums;}
table.mistakes td:first-child{font-weight:600;}
.dl-link{margin:-10px 0 20px; font-size:13.5px;} .dl-link a,.chart-note a,.footer a{color:var(--accent);}
.chart.live iframe{display:block; width:100%; border:0; border-radius:4px; background:#fff;}
.footer{margin-top:40px; padding-top:16px; border-top:1px solid var(--rule); font-size:13.5px; color:var(--muted);}
@media (max-width:520px){ body{font-size:16px; padding-block:24px 48px;} }
@media (prefers-reduced-motion:reduce){ *{transition:none!important;} }
"""


# Чарты дашборда в Yandex DataLens (публичные, домен datalens.yandex разрешает встраивание).
# Под графиком страницы — ссылка на чарт с теми же данными; для двух чартов — живая вставка,
# там, где интерактивность добавляет то, чего нет на картинке.
DL = "https://datalens.yandex/"
DL_DASH = DL + "151am5wmftd4k"
DL_LINKS = {
    "supply_demand": "x1x3xothodp0g", "revpar_monthly": "w0w2a96ebvaef", "check_2026": "lplsheivjvz44",
    "cities": "y2y507iax19mh", "msk_spb": "lplsheivjvz44", "wages": "ptpvxitqq1rs8",
    "fo_shares": "595dvf0vvd9go", "tension": "y2y6j3qnjstqh", "lost": "7b7eq0mrb780q",
    "seasons": "2629p0en9uael", "economy": "lplsheivjvz44", "stress": "x1x47zimoy68g",
    "forecast": "gkgnml5xclpyz", "quality": "484c00avsjqen",
}
DL_EMBEDS = {
    "fo_shares": ("595dvf0vvd9go", "Доля федеральных округов в числе гостей России, 2015–2025, %", 470,
                  "Живой график из DataLens: наведите на линию, чтобы увидеть значение; щелчок по округу в "
                  "легенде скрывает его линию. Росстат (S21)."),
}


def dl_link(chart_id):
    return (f'<p class="dl-link"><a href="{DL}{chart_id}" target="_blank" rel="noopener">'
            f'Открыть интерактивно в DataLens ↗</a></p>')


def dl_embed(chart_id, title, height, note):
    src = f"{DL}{chart_id}?_embedded=1&_no_controls=1"
    return (f'<figure class="chart live"><figcaption class="chart-title">{title}</figcaption>'
            f'<iframe src="{src}" title="{esc(title)}" loading="lazy" style="height:{height}px"></iframe>'
            f'<p class="chart-note">{note} Если не загрузилось — '
            f'<a href="{DL}{chart_id}" target="_blank" rel="noopener">откройте его в DataLens</a>.</p></figure>')


def main():
    html = markdown.markdown(MD.read_text(encoding="utf-8"), extensions=["tables"])
    charts = {
        "kpi": kpi_tiles(), "revisions": chart_revisions(), "calibration": chart_calibration(),
        "supply_demand": chart_supply_demand(), "revpar_monthly": chart_revpar_monthly(),
        "check_2026": chart_check_2026(), "cities": chart_cities(), "msk_spb": chart_msk_spb(),
        "wages": chart_wages(), "fo_shares": chart_fo_shares(), "tension": chart_tension(),
        "lost": chart_lost(), "seasons": chart_seasons(), "economy": chart_economy(), "uae": chart_uae(),
        "stress": chart_stress(), "forecast": chart_forecast(), "actions": chart_actions(),
        "mistakes": chart_mistakes(), "quality": chart_quality(),
        "author": author_block(), "sources": chart_sources(),
    }
    for name, block in charts.items():
        marker = f"<!-- chart:{name} -->"
        assert marker in html, f"нет места для графика {name}"
        if name in DL_EMBEDS:
            block += dl_embed(*DL_EMBEDS[name])
        elif name in DL_LINKS:
            block += dl_link(DL_LINKS[name])
        html = html.replace(marker, block)
    html = html.replace("<table>", '<div class="table-wrap"><table>').replace("</table>\n", "</table></div>\n")
    page = f"""<title>Гостиничный рынок Петербурга</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>{CSS}</style>
<main class="page">
<p class="eyebrow">Портфолио-кейс анализа данных · Максим Поципух · Октябрь 2026</p>
{html}
<p class="footer">Наведите курсор на точку или столбик, чтобы увидеть значение. Те же данные — на
<a href="{DL_DASH}" target="_blank" rel="noopener">дашборде в Yandex DataLens</a>. Данные, скрипты
извлечения и SQL-запросы — в <a href="{REPO}" target="_blank" rel="noopener">репозитории проекта</a>.
Вопросы, гипотезы и проверка выводов — автора; сбор и обработка данных, расчёты и тексты выполнены
с помощью Claude (Anthropic).</p>
</main>
"""
    OUT.write_text(page, encoding="utf-8")
    # Та же страница как самостоятельный HTML-файл для GitHub Pages (папка docs/)
    docs = ROOT / "docs" / "index.html"
    docs.parent.mkdir(exist_ok=True)
    title, body_part = page.split("\n", 1)          # первая строка — <title>
    docs.write_text('<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
                    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                    f'{title}\n<style>body{{margin:0}} img{{max-width:100%}}</style>\n'
                    f'</head>\n<body>\n{body_part}</body>\n</html>\n', encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)} и docs/index.html: {len(page) // 1024} КБ, блоков с инфографикой: {len(charts)}")


if __name__ == "__main__":
    main()
