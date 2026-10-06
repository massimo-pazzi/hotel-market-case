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

import json
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
def chart_revisions():
    # Только напечатанные значения: таблица «Основные показатели» на с. 2 каждого обзора
    ind = {(r["period"], r["source_id"]): num(r["value"]) for r in q(
        """SELECT source_id, period, value FROM indicators
           WHERE metric = 'adr' AND period IN ('2023', '2024') AND period_type = 'год'""")}
    rows = [("2023 год — в обзоре за 2023 год", ind[("2023", "S9")], "s3"),
            ("2023 год — в обзоре за 2024 год", ind[("2023", "S3")], "s2"),
            ("2024 год — в обзоре за 2024 год", ind[("2024", "S3")], "s2"),
            ("2024 год — в обзоре за 2025 год", ind[("2024", "S1")], "s1")]
    d23 = (ind[("2023", "S3")] / ind[("2023", "S9")] - 1) * 100
    d24 = (ind[("2024", "S1")] / ind[("2024", "S3")] - 1) * 100
    svg, h = hbars(rows, 0, 10000, 2000, label_w=250, row_h=26, value_fmt=lambda v: f"{fmt_int(v)} ₽")
    return figure(svg, "Средняя цена номера за 2023 и 2024 годы в разных выпусках обзора NF Group, ₽",
                  f"Каждый новый обзор приводит цену прошлого года заново, и она не совпадает с опубликованной годом "
                  f"раньше: цену 2023 года подняли на {fmt(d23, 0)}%, цену 2024 года — на {fmt(d24, 1)}%. "
                  "Поэтому рост за год нельзя считать по цифрам из разных выпусков. Источник — таблицы «Основные "
                  "показатели» на с. 2 обзоров за 2023, 2024 и 2025 годы.",
                  h, "Горизонтальные столбики: цена номера за 2023 и 2024 годы в разных выпусках обзора")


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
    svg = line_chart([("Номерной фонд", rooms, "s1", f"Номера: +{fmt(rooms[-1] - 100, 0)}%"),
                      ("Турпоток", tour, "s2", f"Туристы: +{fmt(tour[-1] - 100, 0)}%")],
                     years, 0, 180, 30, bands=[(3.5, 5.5, "ковид")])
    return figure(svg, "Номерной фонд и турпоток Петербурга: рост к 2019 году",
                  f"(2019 год = 100 пунктов). Значение {fmt(rooms[-1], 0)} в 2025 году означает, что номеров на {fmt(rooms[-1] - 100, 0)}% больше, "
                  f"чем в 2019-м. Средний номерной фонд качественных отелей — оценка по графикам обзора NF Group "
                  "за 2025 год; турпоток — Комитет по развитию туризма в том же обзоре.", 290,
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
                  "RevPAR = цена × загрузка; цена — оценка по графику NF Group, загрузка — подписи графика.",
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
                   "IBC — данные Hotel Advisors; Vertical Hotels — в пресс-релизе Becar.", h1,
                   "Столбики: рост цены в I полугодии 2025 и 2026 годов по двум источникам") +
            figure(s2, "I полугодие 2026 года к I полугодию 2025-го: загрузка, п. п.; число гостей, %",
                   "IBC, Becar, Росстат в отчёте IBC. Выборки разные — сравнивается направление.",
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
                   "Данные Hotel Advisors в отчёте IBC (с. 13). IBC приводит их как примеры групп городов.",
                   h1, "Горизонтальные столбики: изменение RevPAR по городам, Петербург выделен") +
            figure(s2, "Число гостей в средствах размещения, январь–май 2026 года к 2025-му, %",
                   "Росстат в отчёте IBC (с. 8 и 32).", h2,
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
                   "Данные Hotel Advisors в отчёте IBC (с. 19 и 27); доход на номер = цена × загрузка.",
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
    svg = line_chart([("Зарплата в гостиницах и общепите", wage, "s2", f"Зарплаты: +{fmt(wage[-1] - 100, 0)}%"),
                      ("Цена номера", adr, "s1", f"Цена номера: +{fmt(adr[-1] - 100, 0)}%"),
                      ("Доход на номер", rev, "s3", f"Доход на номер: +{fmt(rev[-1] - 100, 0)}%"),
                      ("Инфляция в Петербурге", cpi, "s4", f"Инфляция: +{fmt(cpi[-1] - 100, 0)}%")],
                     [r["year"] for r in rows], 0, 250, 50, label_w=170)
    return figure(svg, "Цена номера, доход на номер, зарплаты и инфляция: рост к 2019 году",
                  f"(2019 год = 100 пунктов). Значение {fmt(wage[-1], 0)} у зарплат в 2025 году означает, что они "
                  f"выросли на {fmt(wage[-1] - 100, 0)}% к 2019-му. Цена и доход на номер — оценка по графикам обзора "
                  "NF Group за 2025 год; зарплата — Росстат, по России, гостиницы вместе с общепитом; инфляция — "
                  "Росстат, Петербург, декабрь к декабрю.",
                  290, "Линейный график: индексы цены номера, дохода на номер, зарплат и инфляции")


def chart_fo_shares():
    rows = q("""WITH s AS (SELECT r.region, r.year, r.guests*100.0/ru.guests AS sh FROM regions r
                JOIN regions ru ON ru.year=r.year AND ru.level='страна' WHERE r.level='федеральный округ')
                SELECT region, MAX(sh) FILTER (WHERE year=2025) - MAX(sh) FILTER (WHERE year=2019) AS d
                FROM s GROUP BY region ORDER BY d DESC""")
    data = [(r["region"].replace(" федеральный округ", ""), num(r["d"]), "s1" if num(r["d"]) >= 0 else "s2") for r in rows]
    svg, h = hbars(data, -6, 2, 1, "", label_w=170, row_h=22, value_fmt=lambda v: f"{fmt(v, 1, plus=True)} п. п.")
    return figure(svg, "Изменение доли округа в числе гостей России, 2019 → 2025, п. п.",
                  "Росстат, все средства размещения и все цели поездок.", h,
                  "Горизонтальные столбики: изменение доли федеральных округов в числе гостей")


def chart_tension():
    names = ["г.Москва", "Приморский край", "г.Санкт-Петербург", "Московская область", "Новосибирская область",
             "Свердловская область", "Челябинская область", "Волгоградская область",
             "Тюменская область (кроме Ханты-Мансийского автономного округа-Югры и Ямало-Ненецкого автономного округа)"]
    rows = q(f"""SELECT region, MAX(guests*1.0/rooms) FILTER (WHERE year=2019) AS g19,
                 MAX(guests*1.0/rooms) FILTER (WHERE year=2025) AS g25 FROM regions
                 WHERE region IN ({",".join("'" + n + "'" for n in names)}) GROUP BY region
                 ORDER BY g25/g19""")
    spb = next((num(r["g19"]), num(r["g25"])) for r in rows if r["region"] == "г.Санкт-Петербург")
    x0, x1, top, rh = 190, W - 60, 10, 24
    lo, hi = 40, 200
    height = top + len(rows) * rh + 30
    yb = top + len(rows) * rh
    out = [xgrid(lo, hi, 20, x0, x1, top, yb)]
    for i, r in enumerate(rows):
        yc = top + i * rh + rh / 2
        a, b = num(r["g19"]), num(r["g25"])
        Xa, Xb = sc(a, lo, hi, x0, x1), sc(b, lo, hi, x0, x1)
        name = r["region"].replace("г.", "").replace(
            " (кроме Ханты-Мансийского автономного округа-Югры и Ямало-Ненецкого автономного округа)", " (юг)").replace("Тюменская область", "Тюменская обл.")
        cls = "s2" if b < a else "s1"
        out.append(f'<text class="rowlabel {"strong" if "Петербург" in name else ""}" x="{x0 - 8}" y="{yc + 4:.1f}" text-anchor="end">{esc(name)}</text>')
        out.append(f'<line class="connector" x1="{Xa:.1f}" x2="{Xb:.1f}" y1="{yc:.1f}" y2="{yc:.1f}"/>')
        out.append(f'<circle class="dot hollow" cx="{Xa:.1f}" cy="{yc:.1f}" r="4.5"><title>{esc(name)}, 2019: {fmt(a, 0)}</title></circle>')
        out.append(f'<circle class="dot {cls}" cx="{Xb:.1f}" cy="{yc:.1f}" r="5.5"><title>{esc(name)}, 2025: {fmt(b, 0)}</title></circle>')
        out.append(f'<text class="value" x="{max(Xa, Xb) + 9:.1f}" y="{yc + 4:.1f}">{fmt((b / a - 1) * 100, 0, plus=True)}%</text>')
    return (legend([("2019", "hollow"), ("2025: гостей на номер больше", "s1"), ("2025: меньше", "s2")]) +
            figure("".join(out), "Гостей в год на один номер, 2019 → 2025",
                   f"Сколько гостей за год приходится на один номер: число людей, которые заселились в средства "
                   f"размещения региона, делённое на число номеров (Росстат). Полый кружок — 2019 год, закрашенный — "
                   f"2025-й, справа — изменение. В Петербурге на номер приходилось {fmt_int(spb[0])} гостей в год, "
                   f"стало {fmt_int(spb[1])}: номеров построили больше, чем прибавилось гостей, и за каждого гостя "
                   "отелям приходится конкурировать сильнее. Там, где показатель растёт, гостей прибавляется "
                   "быстрее, чем номеров.",
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
                  "оценены по цене 2025 года, обзор NF Group за 2025 год.", 240,
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
                   "NF Group: цена — оценка по графику, загрузка — подписи графика (целые проценты).", 200,
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
            f'больше гостей</figcaption>{html}<p class="chart-note">IBC: I пол. 2025 — загрузка {fmt(o25, 0)}%, '
            f'цена {fmt(a25, 1)} тыс. ₽. Наблюдаемая чувствительность загрузки к цене — {fmt(e, 2)} '
            f'(1% цены ≈ 1% гостей); вариант «+4%» рассчитан по ней.</p></figure>')


def chart_uae():
    rows = context("ОАЭ 2026")
    seq = [("январь–февраль 2026", "янв–фев"), ("неделя до 14.03.2026", "сер. марта"), ("март 2026", "март"),
           ("июнь 2026", "июнь"), ("август 2026", "август")]
    occ = {r["period"]: r for r in rows if r["metric"] == "Загрузка отелей Дубая"}
    vals = [num(occ[p]["value"]) for p, _ in seq]
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
    d19 = context("Дубай 2019")
    data = [(r["metric"], num(r["value"]), "s1" if num(r["value"]) >= 0 else "s2") for r in d19]
    s2, h2 = hbars(data, -20, 15, 5, "%", label_w=240, row_h=24)
    return (figure("".join(out), "Загрузка отелей Дубая в 2026 году",
                   "Сплошные точки — независимые консультанты (HVS/CoStar, JLL), полые — официальная статистика "
                   "туристического департамента Дубая за месяц. Пассажиропоток аэропорта Дубая в I полугодии −31%.",
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
    grid = [("Командировки −10%, деловых гостей 11%", v["стресс: всё + налог"]),
            ("Командировки −10%, деловых гостей 20%", v["стресс: всё + налог, доля бизнеса 20%"]),
            ("Командировки −20%, деловых гостей 11%", v["стресс: всё + налог, командировки −20%"]),
            ("Командировки −20%, деловых гостей 20%", v["стресс: всё + налог, командировки −20%, доля бизнеса 20%"])]
    assert fmt(grid[2][1], 1) == "−0,6" and fmt(grid[3][1], 1) == "−2,5", "текст шага 14 разошёлся с расчётом"
    s2, h2 = hbars([(n, x, "s1" if x >= 0 else "s2") for n, x in grid], -3, 2, 1, "%", label_w=280, row_h=26,
                   value_fmt=lambda x: f"{fmt(x, 1, plus=True)}%")
    return (figure("".join(out), "Рост дохода на номер в 2027 году: базовый сценарий и стресс-вариант, %",
                   "Расчёт — sql/analysis/forecast_2027.sql. Падение автопоездок и командировок на 10% — "
                   "сценарные допущения, не прогноз.", H, "Каскадная диаграмма: что съедает рост дохода на номер в 2027 году") +
            figure(s2, "Итог стресс-варианта при разных допущениях о командировках: рост дохода на номер в 2027 году, %",
                   "Во всех строках учтены топливо и туристический налог за счёт отеля. Доля деловых гостей 11% — оценка "
                   "Комитета по развитию туризма в пересказе СМИ, не сверена; 20% — если деловые гости живут в отелях "
                   "чаще остальных. Падение командировок на 10% и 20% — допущения.", h2,
                   "Столбики: итог стресс-варианта при четырёх сочетаниях допущений"))


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
                  "Факт — подписи графика обзора NF Group за 2025 год, 2025 — 63,7% по таблице. Сценарии — "
                  "sql/analysis/forecast_2027.sql.", 290, "Линейный график загрузки: факт и три сценария")


def table(head, rows, cls="actions"):
    return (f'<div class="table-wrap"><table class="{cls}"><thead><tr>' + "".join(f"<th>{h}</th>" for h in head) +
            "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) +
            "</tbody></table></div>")


def chart_actions():
    # Наблюдение по рынку → что оно может значить → чем проверить у себя. Средние не
    # предписание, а повод для проверки на собственных данных отеля.
    return table(["Что видно по рынку", "Что это может значить", "Чем проверить у себя"], [
        ["Загрузка 2027 года — около 60% в базовом сценарии и 56–58% с налоговыми и топливными рисками, "
         "против 63,7% в 2025-м (шаги 14–15)",
         "Бюджет, свёрстанный от загрузки 2025 года, скорее всего, может быть завышен",
         "Сравнить свою загрузку 2025 года с рынком и сдвинуть план на ту же разницу; в январе–феврале "
         "смотреть, как набираются бронирования на 2027 год"],
        ["В январе–апреле 2025 года рынок поднял цену на 11–18% без потери загрузки (шаг 11)",
         "Запас цены в эти месяцы был у рынка в среднем",
         "Сравнить свой рост цены за те же месяцы с рынком: если вы уже подняли больше, запас выбран"],
        ["Летом и осенью 2025 года загрузка упала на 3–7 пунктов при росте цен на 4–18% (шаги 10–11)",
         "Туристы, у которых есть выбор, ушли к конкурентам, в квартиры или в другие города",
         "Найти месяцы, где ваша загрузка упала сильнее рынка, и посмотреть, в каких каналах продаж"],
        ["Скидки не вернули гостей: Москва −9% дохода на номер, Дубай 2019 года −16% (шаги 8, 13)",
         "В остывающем рынке ценовая война съедает доход, а гостей не возвращает",
         "Сравнить загрузку до и после своих прошлых скидок с тем, что за это время сделал рынок"],
        ["В экономсегменте рост цены на 17% съела потеря гостей (шаг 12)",
         "Гость экономсегмента чувствительнее к цене, чем рынок в среднем",
         "Посчитать, как меняется загрузка при изменении цены, на своих дневных данных"],
        ["Зарплаты в гостиницах и общепите +24% против дохода на номер +8% в 2025 году (шаг 9)",
         "Затраты на персонал растут быстрее выручки",
         "Посчитать фонд оплаты труда на занятый номер по месяцам"],
        ["Спрос идёт за доступностью: Калининград, Дубай; стресс-вариант съедает рост 2027 года (шаги 13–14)",
         "Главные риски 2027 года — Пулково, ограничения полётов, топливо, налоговые проверки",
         "Оценить, какая доля ваших гостей прилетает, а какая приезжает на машине, какая доля деловых туристов"],
    ], cls="actions hyp")


def chart_kaliningrad():
    rows = {r["metric"]: r for r in context("Калининград 2026")}
    fl = rows["Перелёт из Москвы туда и обратно на человека"]
    dr = rows["Снижение показателей сильных новых объектов к 2024 году"]
    tiles = [(f"{fl['value']} тыс. ₽", "перелёт из Москвы в Калининград и обратно на одного человека"),
             ("−30–40%", "показатели сильных новых отелей в 2026 году к 2024-му, местами до −50%, — несмотря на снижение цен")]
    assert dr["value"] == "30–40 (местами 50)", "плитка Калининграда разошлась с data/context"
    return ('<figure class="chart"><figcaption class="chart-title">Калининград, 2026 год: спрос упёрся в стоимость дороги</figcaption>'
            '<div class="kpis">' + "".join(
                f'<div class="kpi"><div class="kpi-v">{esc(v)}</div><div class="kpi-l">{esc(l)}</div></div>' for v, l in tiles) +
            '</div><p class="chart-note">Оценка Hotel Advisors, выступление С. Данильченко 15.09.2026. '
            'Это экспертная оценка, а не опубликованный ряд данных.</p></figure>')


def chart_ha_compare():
    fc = {r["scenario"].strip('"'): r for r in sql_file_table("sql/analysis/forecast_2027.sql", "scenario,fund_2026")}
    b = fc["базовый"]
    ha = {r["metric"]: r["value"] for r in context("Россия 2026–2027")}
    adr_g = (num(b["adr_2027"]) / num(b["adr_2026"]) - 1) * 100
    flat = (num(b["occ_2027"]) / num(b["occ_2026"]) - 1) * 100   # доход на номер, если цена 2027 = цене 2026
    assert -2.5 < flat < -1.5, "текст шага 15 говорит «примерно на 2%»"
    st = [r for r in sql_file_table("sql/analysis/forecast_2027.sql", "variant,demand_2027_pct")
          if r["variant"].strip('"').startswith("стресс: всё + налог")]
    s_occ = [num(r["occ_2027"]) for r in st]
    s_rev = [num(r["revpar_2027_pct"]) for r in st]
    assert (round(min(s_occ)), round(max(s_occ))) == (56, 58), "текст: «56–58%»"
    assert (fmt(max(s_rev), 1), fmt(min(s_rev), 1)) == ("0,5", "−2,5"), "текст: «от +0,5% до −2,5%»"
    rows = [
        ["Загрузка в 2026 году", f"{ha['Загрузка с начала 2026 года']}% с начала года",
         f"{fmt(num(b['occ_2026']), 1)}% против 63,7% в 2025-м", "направление совпадает"],
        ["Загрузка в 2027 году", ha["Загрузка в 2027 году"],
         f"{fmt(num(b['occ_2027']), 1)}%, снижение замедляется; с рисками шага 14 — "
         f"{fmt(min(s_occ), 0)}–{fmt(max(s_occ), 0)}%", "совпадает, если риски не сработают"],
        ["Средняя цена в 2027 году", ha["Средний тариф в 2027 году"],
         f"+{fmt(adr_g, 0)}%, около инфляции", "<strong>расходится</strong>"],
        ["Доход на номер в 2027 году", "—",
         f"+{fmt(num(b['revpar_2027_pct']), 1)}%; если цена не вырастет — {fmt(flat, 1)}%; с рисками шага 14 — "
         f"от {fmt(max(s_rev), 1, plus=True)}% до {fmt(min(s_rev), 1)}%", "зависит от цены и рисков"],
    ]
    return (table(["", "Hotel Advisors, вся Россия", "Мой базовый сценарий, качественные отели Петербурга", "Итог"],
                  rows, cls="compare-t") +
            '<p class="chart-note">Объекты разные: у Hotel Advisors — вся страна с большим весом Москвы и Сочи, у меня — '
            'качественные отели Петербурга по данным NF Group. Сравнивать можно направление, не уровни. '
            'Сценарий — sql/analysis/forecast_2027.sql.</p>')


def chart_next():
    return table(["Что исследовать", "На каких данных", "На какой вопрос ответит"], [
        ["Положение отеля относительно конкурентов", "Компсет, помесячно за три года и больше: загрузка, цена, доход на номер",
         "Отстаёт ли отель от рынка и в чём — в загрузке, цене или доходе на номер"],
        ["Темп бронирований на 2027 год", "Свои бронирования на будущие даты и темп их набора, в идеале — по конкурентам",
         "Подтверждается ли сценарий загрузки около 60% уже в январе–феврале"],
        ["Сегментация спроса", "Свои продажи: деловые, туристы, группы; прямые продажи и агрегаторы",
         "Сколько у вас деловых гостей: несверенная доля 11% или 20% переворачивает стресс-вариант (+0,5% или −0,4%)"],
        ["Чувствительность гостей к цене", "Дневные цены и загрузка одного отеля",
         "На сколько падает загрузка при росте цены — на десяти годовых точках рынка это не посчитать"],
        ["Доступность как опережающий индикатор", "Пассажиропоток Пулково по месяцам, цены авиабилетов, топливо, ограничения полётов",
         "Когда ждать спада или восстановления спроса — до того, как он виден в загрузке"],
        ["Квартиры и апартаменты", "Предложение и цены посуточной аренды на площадках бронирования",
         "Есть ли переток гостей из отелей в квартиры — пока это непроверенная гипотеза"],
        ["Затраты", "Отчётность отеля по USALI, фонд оплаты труда",
         "Сколько стоит номер в обслуживании и можно ли держать штат под загрузку — расчёт вместо совета"],
    ], cls="next")


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
    ("S20", "Федеральный закон от 28.11.2025 № 425-ФЗ: НДС 22% и снижение порога УСН"),
    ("S22", "Hotel Advisors, «Загрузка снижается, рост тарифа замедляется: что происходит с гостиничным рынком России», С. Данильченко, 15.09.2026"),
    ("S23", "Hotel Advisors, «Бюджет отеля на следующий год: как учитывать динамику рынка», А. Ванцян, 28.09.2026"),
    ("S24", "Клерк, «ФНС ужесточает борьбу с «бумажным» НДС», 07.09.2026"),
    ("S25", "Налоговый кодекс РФ, статья 89 «Выездная налоговая проверка», п. 4"),
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
    return (f'<div class="author"><a href="https://massimo-pazzi.github.io/" title="Все кейсы автора"><img src="data:image/jpeg;base64,{img}" alt="Максим Поципух" width="64" height="64"></a>'
            '<span class="author-txt"><a class="author-name" href="https://massimo-pazzi.github.io/" title="Все кейсы автора">Максим Поципух</a><span class="author-links">Maxim Potsipukh · '
            '<a href="https://t.me/maxim_potsipukh" target="_blank" rel="noopener">Telegram</a> · '
            '<a href="https://max.ru/u/f9LHodD0cOI-rqGbPaCc2EshAXaEgw4ABwO8e2-ng4zK-otGeBnO04IzH5g" target="_blank" rel="noopener">Max</a></span></span></div>')


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
h3{font-size:1.06rem; line-height:1.35; font-weight:650; margin:30px 0 10px;}
table.hyp td{font-size:14px;} table.hyp td:first-child{font-weight:500;} table.actions.hyp td:last-child{font-weight:400;}
table.compare-t td:first-child,table.next td:first-child{font-weight:600;}
h1 + p em,.author + p em{color:var(--ink-2); font-size:15px;} .author + p a,p a{color:var(--accent);}
.author{display:flex; align-items:center; gap:12px; margin:4px 0 16px; font-weight:600; font-size:15px;}
.author img{width:64px; height:64px; border-radius:50%; object-fit:cover; border:1px solid var(--rule);}
.author-txt{display:flex; flex-direction:column; gap:2px;} .author-name{color:inherit; text-decoration:none;} .author-name:hover{color:var(--accent); text-decoration:underline;} .author a img{display:block;} .author-links{font-weight:400; font-size:13.5px; color:var(--muted);} .author-links a{color:var(--accent);}
.sources{font-size:14.5px; line-height:1.55; padding-left:1.5em;} .sources li{margin-bottom:6px;}
.sources a{color:var(--accent); word-break:break-word;} .sid{font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:12px; color:var(--muted); margin-right:4px;}
.sources-h{margin:14px 0 6px; font-weight:600; font-size:14.5px;}
ol.sources{list-style:none; padding-left:0;}

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
    "forecast": "gkgnml5xclpyz",
}
DL_EMBEDS = {
    "fo_shares": ("595dvf0vvd9go", "Доля федеральных округов в числе гостей России, 2015–2025, %", 470,
                  "Живой график из DataLens: наведите на линию, чтобы увидеть значение; щелчок по округу в "
                  "легенде скрывает его линию. Росстат."),
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



# Блок «Другие кейсы автора» — одинаковый во всех кейсах портфолио, ставится над источниками.
OTHER_CASES = [
    ("hotel-market-case", "Анализ рынка", "Рост цен в отелях Петербурга перестал окупаться"),
    ("housing-digital-twin-case", "Новый продукт", "Цифровой двойник жилого фонда Москвы: от аварийного ремонта к прогнозу поломок"),
    ("b2b-value-case", "Обоснование проекта", "Как доказать окупаемость ИИ-проекта, не зная маржи заказчика"),
    ("fastfood-assistant-case", "Продукт с ИИ", "ИИ-ассистент для федеральной сети быстрого питания: как спроектировать продукт не имея данных заказчика"),
    ("rief-2026-talk", "Стратегия и аналитика рынка", "Интерфейс энергетики будущего: доклад на РМЭФ-2026"),
    ("wine-ai-case", "Категорийный маркетинг", "ИИ-сомелье для сети супермаркетов: при каких условиях он может окупиться"),
]


def other_cases(current):
    tiles = "".join(
        f'<a class="oc-tile" href="https://massimo-pazzi.github.io/{slug}/"><span class="oc-tag">{tag}</span>'
        f'<span class="oc-title">{title}</span><span class="oc-go">Открыть кейс →</span></a>'
        for slug, tag, title in OTHER_CASES if slug != current)
    style = ("<style>.oc-grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:10px; margin:12px 0 8px;}"
             ".oc-tile{display:flex; flex-direction:column; gap:6px; padding:14px 16px; background:var(--surface); border:1px solid var(--rule);"
             " border-radius:6px; text-decoration:none; color:inherit;} .oc-tile:hover{border-color:var(--accent);}"
             ".oc-tag{font-size:12px; letter-spacing:.04em; text-transform:uppercase; color:var(--accent);}"
             ".oc-title{font-weight:600; font-size:15px; line-height:1.35;} .oc-go{margin-top:auto; font-size:13px; color:var(--accent);}</style>")
    return f'{style}<h2>Другие кейсы автора</h2><div class="oc-grid">{tiles}</div>\n'


# SEO: заголовок, описание, автор, canonical, Open Graph и JSON-LD — одинаково во всех кейсах портфолио.
AUTHOR = {"@type": "Person", "name": "Максим Поципух", "alternateName": "Maxim Potsipukh",
          "sameAs": ["https://t.me/maxim_potsipukh",
                     "https://max.ru/u/f9LHodD0cOI-rqGbPaCc2EshAXaEgw4ABwO8e2-ng4zK-otGeBnO04IzH5g",
                     "https://github.com/massimo-pazzi"]}
OG_IMAGE = "https://massimo-pazzi.github.io/rief-2026-talk/assets/img/og.jpg"
SEO = {
    "hotel-market-case": ("Гостиничный рынок Петербурга — Максим Поципух",
                          "Рост цен в отелях Петербурга перестал окупаться",
                          "Исследование Максима Поципуха по открытым данным: почему рост цен в отелях Петербурга "
                          "перестал окупаться — спрос и номерной фонд, сезонность, сегменты, города и прогноз."),
    "housing-digital-twin-case": ("Цифровой двойник ЖКХ — Максим Поципух",
                                  "Цифровой двойник жилого фонда Москвы: от аварийного ремонта к прогнозу поломок",
                                  "Продуктовый кейс Максима Поципуха: цифровой двойник жилого фонда Москвы и прогноз "
                                  "отказов инженерных систем домов — для кого продукт, метрики, прототип, этапы внедрения."),
    "b2b-value-case": ("Окупаемость без маржи — Максим Поципух",
                       "Как доказать окупаемость ИИ-проекта, не зная маржи заказчика",
                       "Кейс Максима Поципуха: обоснование ИИ-проекта для грузовой авиакомпании — цена бездействия, "
                       "две картины ценности и пороговая маржа, которую заказчик проверяет сам."),
    "fastfood-assistant-case": ("ИИ-ассистент без данных — Максим Поципух",
                                "ИИ-ассистент для федеральной сети быстрого питания: как спроектировать продукт не имея данных заказчика",
                                "Продуктовый кейс Максима Поципуха: ИИ-ассистент в приложении федеральной сети быстрого "
                                "питания — темы обращений, границы продукта, очерёдность релизов, нагрузка, экономика и риски."),
    "wine-ai-case": ("ИИ-сомелье для сети супермаркетов — Максим Поципух",
                     "ИИ-сомелье для сети супермаркетов: при каких условиях он может окупиться",
                     "Кейс Максима Поципуха по категорийному маркетингу: ИИ-консультант по вину для сети супермаркетов — "
                     "объём категории, эффект в выручке и в марже с учётом охвата, порог окупаемости, правовые ограничения и MVP."),
    "rief-2026-talk": ("Интерфейс энергетики будущего — Максим Поципух",
                       "Интерфейс энергетики будущего: доклад на РМЭФ-2026",
                       "Доклад Максима Поципуха на Российском международном энергетическом форуме 2026: как "
                       "искусственный интеллект меняет взаимодействие человека с энергетической инфраструктурой."),
}


def seo_head(slug):
    title, headline, desc = SEO[slug]
    url = f"https://massimo-pazzi.github.io/{slug}/"
    ld = {"@context": "https://schema.org", "@type": "Article", "headline": headline, "description": desc,
          "inLanguage": "ru", "url": url, "mainEntityOfPage": url, "image": OG_IMAGE, "author": AUTHOR}
    q = lambda t: t.replace("&", "&amp;").replace('"', "&quot;")
    return (f'<title>{title}</title>\n'
            f'<meta name="description" content="{q(desc)}">\n'
            f'<meta name="author" content="Максим Поципух (Maxim Potsipukh)">\n'
            f'<link rel="canonical" href="{url}">\n'
            f'<meta property="og:type" content="article">\n'
            f'<meta property="og:locale" content="ru_RU">\n'
            f'<meta property="og:site_name" content="Максим Поципух — портфолио">\n'
            f'<meta property="og:title" content="{q(title)}">\n'
            f'<meta property="og:description" content="{q(desc)}">\n'
            f'<meta property="og:url" content="{url}">\n'
            f'<meta property="og:image" content="{OG_IMAGE}">\n'
            f'<meta name="twitter:card" content="summary_large_image">\n'
            f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>')


def apply_seo(page, slug):
    """Заменяет <title> и description страницы на SEO-блок."""
    page = re.sub(r'<meta name="description" content="[^"]*">\n?', "", page)
    return re.sub(r"<title>[^<]*</title>", lambda m: seo_head(slug), page, count=1)


def main():
    html = markdown.markdown(MD.read_text(encoding="utf-8"), extensions=["tables"])
    charts = {
        "revisions": chart_revisions(), "calibration": chart_calibration(),
        "supply_demand": chart_supply_demand(), "revpar_monthly": chart_revpar_monthly(),
        "check_2026": chart_check_2026(), "cities": chart_cities(), "msk_spb": chart_msk_spb(),
        "wages": chart_wages(), "fo_shares": chart_fo_shares(), "tension": chart_tension(),
        "lost": chart_lost(), "seasons": chart_seasons(), "economy": chart_economy(), "uae": chart_uae(),
        "stress": chart_stress(), "forecast": chart_forecast(), "actions": chart_actions(),
        
        "kaliningrad": chart_kaliningrad(), "ha_compare": chart_ha_compare(), "next": chart_next(),
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
<p class="eyebrow">Портфолио-кейс по анализу данных · Максим Поципух · Октябрь 2026</p>
{html}
</main>
"""
    page = page.replace("<h2>Источники</h2>", other_cases("hotel-market-case") + "<h2>Источники</h2>", 1)
    OUT.write_text(page, encoding="utf-8")
    # Та же страница как самостоятельный HTML-файл для GitHub Pages (папка docs/)
    docs = ROOT / "docs" / "index.html"
    docs.parent.mkdir(exist_ok=True)
    title, body_part = page.split("\n", 1)          # первая строка — <title>
    docs.write_text('<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
                    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                    f'{seo_head("hotel-market-case")}\n<style>body{{margin:0}} img{{max-width:100%}}</style>\n'
                    f'</head>\n<body>\n{body_part}</body>\n</html>\n', encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)} и docs/index.html: {len(page) // 1024} КБ, блоков с инфографикой: {len(charts)}")


if __name__ == "__main__":
    main()
