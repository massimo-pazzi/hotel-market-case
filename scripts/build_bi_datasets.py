"""Готовит наборы данных для дашборда в Yandex DataLens: dashboard/data/*.csv.

Каждый файл — одна тема, «длинный» формат, понятные названия колонок, даты в
ISO, расчётные показатели (изменения к прошлому году, индексы) посчитаны
заранее теми же запросами DuckDB, что и в sql/analysis/. Источник каждой
строки указан в колонке source.

Запуск:  .venv/bin/python scripts/build_bi_datasets.py
"""

import csv
import io
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dashboard" / "data"
DUCKDB = "/opt/homebrew/bin/duckdb"


def q(sql):
    res = subprocess.run([DUCKDB, "-csv", "-c", ".read sql/setup.sql", "-c", sql],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    # DuckDB выводит пустые значения как NULL — для BI нужна пустая ячейка
    return [{k: ("" if v == "NULL" else v) for k, v in r.items()}
            for r in csv.DictReader(io.StringIO(res.stdout))]


def sql_file_table(path, header_start):
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


# Русские названия колонок: в DataLens они становятся подписями полей и осей
RU = {
    "year": "Год", "month": "Номер месяца", "month_name": "Месяц", "date": "Дата", "season": "Сезон",
    "occupancy_pct": "Загрузка (%)", "adr_rub": "Цена номера ADR (₽)", "revpar_rub": "Доход на номер RevPAR (₽)",
    "rooms_avg": "Номерной фонд средний", "apart_share_pct": "Доля апарт-отелей (%)",
    "domestic_mln": "Внутренний турпоток (млн)", "foreign_mln": "Иностранный турпоток (млн)",
    "tourists_mln": "Турпоток (млн)", "tourists_per_room": "Туристов на номер",
    "rooms_index_2019": "Номерной фонд (2019 = 100)", "tourists_index_2019": "Турпоток (2019 = 100)",
    "wage_hotels_catering_rub": "Зарплата в гостиницах и общепите (₽)", "cpi_spb_dec_dec": "ИПЦ Петербурга дек. к дек. (%)",
    "adr_index_2019": "Цена номера (2019 = 100)", "revpar_index_2019": "Доход на номер (2019 = 100)",
    "cpi_index_2019": "Инфляция (2019 = 100)", "wage_index_2019": "Зарплаты (2019 = 100)",
    "occupancy_change_pp": "Изменение загрузки (п. п.)", "adr_change_pct": "Изменение цены (%)",
    "revpar_change_pct": "Изменение дохода на номер (%)", "lost_revenue_150rooms_mln": "Упущенная выручка на 150 номеров (млн ₽)",
    "city": "Город", "segment": "Сегмент", "period": "Период", "adr_thousand_rub": "Цена номера ADR (тыс. ₽)",
    "revpar_thousand_rub": "Доход на номер RevPAR (тыс. ₽)", "segment_order": "Порядок сегмента",
    "location": "Город", "ibc_group": "Группа IBC", "is_spb": "Петербург",
    "rank": "Место", "region": "Регион", "federal_district": "Федеральный округ", "guests_mln": "Гостей (млн)",
    "change_pct": "Изменение числа гостей (%)", "level": "Уровень", "rooms": "Номеров", "guests": "Гостей",
    "guests_per_room": "Гостей на номер", "guests_share_pct": "Доля в гостях России (%)",
    "rooms_share_pct": "Доля в номерах России (%)", "scenario": "Сценарий", "step_order": "Шаг",
    "variant": "Вариант", "demand_2027_pct": "Спрос 2027 (%)", "occupancy_2027_pct": "Загрузка 2027 (%)",
    "revpar_2027_change_pct": "Рост дохода на номер 2027 (%)", "group": "Группа проверки", "check": "Проверка",
    "expected": "Ожидалось", "actual": "Фактически", "diff": "Разница", "status": "Статус", "note": "Пояснение",
    "metric": "Показатель", "edition": "Код выпуска", "edition_name": "Выпуск", "value": "Значение",
    "source": "Источник",
}
METRIC_RU = {"adr": "Цена номера ADR (₽)", "revpar": "Доход на номер RevPAR (₽)", "occupancy": "Загрузка (%)",
             "rooms_total": "Номерной фонд"}


def period_ru(p):
    return f"I пол. {p[:4]}" if p.endswith("-H1") else p


def write(name, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    missing = [k for k in rows[0] if k not in RU]
    assert not missing, f"нет русского названия для {missing}"
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[RU[k] for k in rows[0]])
        w.writeheader()
        w.writerows({RU[k]: v for k, v in r.items()} for r in rows)
    print(f"dashboard/data/{name}: {len(rows)} строк")


MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август",
          "сентябрь", "октябрь", "ноябрь", "декабрь"]


def season(m):
    return "ноябрь–март" if m in (11, 12, 1, 2, 3) else ("июнь–август" if m in (6, 7, 8) else "апрель–май, сентябрь–октябрь")


def main():
    # 1. Рынок по годам ------------------------------------------------------------
    rows = q("""
        WITH f AS (SELECT year, SUM(start_rooms_est + intake_label / 2.0) AS rooms_avg,
                          SUM(CASE WHEN segment = 'apart' THEN start_rooms_est + intake_label / 2.0 END) AS apart
                   FROM supply_chart WHERE is_forecast = 0 GROUP BY year),
        b AS (SELECT f.rooms_avg AS r19, t.total_mln AS t19 FROM f JOIN tourist_flow t USING (year) WHERE f.year = 2019)
        SELECT a.year, a.occupancy_label AS occupancy_pct, a.adr_est AS adr_rub, a.revpar_est AS revpar_rub,
               ROUND(f.rooms_avg) AS rooms_avg, ROUND(f.apart / f.rooms_avg * 100, 1) AS apart_share_pct,
               t.domestic_mln, t.foreign_mln, t.total_mln AS tourists_mln,
               ROUND(t.total_mln * 1e6 / f.rooms_avg) AS tourists_per_room,
               ROUND(f.rooms_avg / b.r19 * 100, 1) AS rooms_index_2019,
               ROUND(t.total_mln / b.t19 * 100, 1) AS tourists_index_2019
        FROM annual_chart a JOIN f USING (year) JOIN tourist_flow t USING (year) CROSS JOIN b
        ORDER BY a.year""")
    wages = {r["year"]: r for r in q("SELECT * FROM rosstat")}
    base = None
    lvl = 100.0
    for r in rows:
        w = wages.get(r["year"])
        r["wage_hotels_catering_rub"] = w["wage_ru_hotels_catering"] if w else ""
        r["cpi_spb_dec_dec"] = w["cpi_spb_dec_dec"] if w else ""
        r["source"] = "NF Group S1 (цена, доход на номер, фонд — оценка по графику); турпоток — Комитет по туризму; зарплаты, ИПЦ — Росстат"
    # индексы 2019 = 100 для цены, дохода на номер, зарплат и инфляции
    b19 = next(r for r in rows if r["year"] == "2019")
    for r in rows:
        y = int(r["year"])
        r["adr_index_2019"] = round(float(r["adr_rub"]) / float(b19["adr_rub"]) * 100, 1)
        r["revpar_index_2019"] = round(float(r["revpar_rub"]) / float(b19["revpar_rub"]) * 100, 1)
        if y >= 2019 and r["wage_hotels_catering_rub"]:
            if y > 2019:
                lvl *= float(r["cpi_spb_dec_dec"]) / 100
            r["cpi_index_2019"] = round(lvl, 1)
            r["wage_index_2019"] = round(float(r["wage_hotels_catering_rub"]) / float(b19["wage_hotels_catering_rub"]) * 100, 1)
        else:
            r["cpi_index_2019"], r["wage_index_2019"] = "", ""
        r["date"] = f"{y}-01-01"
    write("market_annual.csv", rows)

    # 2. Рынок по месяцам ------------------------------------------------------------
    rows = q("""
        SELECT m.year, m.month, m.occupancy_label AS occupancy_pct, m.adr_est AS adr_rub,
               ROUND(m.adr_est * m.occupancy_label / 100) AS revpar_rub,
               m.occupancy_label - p.occupancy_label AS occupancy_change_pp,
               ROUND((m.adr_est / p.adr_est - 1) * 100, 1) AS adr_change_pct,
               ROUND((m.adr_est * m.occupancy_label / (p.adr_est * p.occupancy_label) - 1) * 100, 1) AS revpar_change_pct,
               ROUND(150 * DAY(LAST_DAY(MAKE_DATE(m.year, m.month, 1))) * (p.occupancy_label - m.occupancy_label)
                     / 100.0 * m.adr_est / 1e6, 2) AS lost_revenue_150rooms_mln
        FROM monthly_chart m LEFT JOIN monthly_chart p ON p.month = m.month AND p.year = m.year - 1
        ORDER BY m.year, m.month""")
    for r in rows:
        m = int(r["month"])
        r["date"] = f"{r['year']}-{m:02d}-01"
        r["month_name"] = MONTHS[m - 1]
        r["season"] = season(m)
        r["source"] = "NF Group S1 с. 7: загрузка — подписи графика, цена — оценка по графику"
    write("market_monthly.csv", rows)

    # 3. Сегменты: Петербург и Москва -------------------------------------------------
    rows = q("""
        SELECT s.city, s.segment, s.period, s.occupancy_pct, s.adr_thousand_rub,
               ROUND(s.occupancy_pct * s.adr_thousand_rub / 100, 2) AS revpar_thousand_rub,
               s.occupancy_pct - p.occupancy_pct AS occupancy_change_pp,
               ROUND((s.adr_thousand_rub / p.adr_thousand_rub - 1) * 100, 1) AS adr_change_pct,
               ROUND((s.occupancy_pct * s.adr_thousand_rub / (p.occupancy_pct * p.adr_thousand_rub) - 1) * 100, 1) AS revpar_change_pct
        FROM ibc_segments s
        LEFT JOIN ibc_segments p ON p.city = s.city AND p.segment = s.segment
             AND p.period = CAST(CAST(LEFT(s.period, 4) AS INT) - 1 AS VARCHAR) || '-H1'
        ORDER BY s.city, s.period""")
    order = {"Экономичный": 1, "Среднеценовой": 2, "Верхний предел среднеценового": 3, "Высокий": 4,
             "Верхний предел высокого": 5, "Люксовый": 6, "Рынок в целом": 7}
    for r in rows:
        r["segment_order"] = order[r["segment"]]
        r["period"] = period_ru(r["period"])
        r["source"] = "IBC Real Estate по данным Hotel Advisors, S13 (январь–июнь)"
    write("segments_h1.csv", rows)

    # 4. Города: RevPAR I пол. 2026 и число гостей ------------------------------------
    rows = q("SELECT location, revpar_change_pct, ibc_group FROM ibc_city_revpar ORDER BY revpar_change_pct")
    for r in rows:
        r["is_spb"] = "да" if r["location"] == "Санкт-Петербург" else "нет"
        r["source"] = "IBC Real Estate по данным Hotel Advisors, S13 с. 13"
    write("cities_revpar_h1_2026.csv", rows)
    rows = q("SELECT rank, region, federal_district, placed_mln AS guests_mln, change_pct FROM ibc_placed ORDER BY rank")
    for r in rows:
        r["period"] = "январь–май 2026"
        r["source"] = "Росстат в отчёте IBC, S13 с. 8 и 32"
    write("regions_guests_jan_may_2026.csv", rows)

    # 5. Регионы 2015–2025 с федеральным округом ----------------------------------------
    rows = q("SELECT region, level, year, rooms, guests FROM regions")
    ru = {r["year"]: r for r in rows if r["level"] == "страна"}
    fo = None
    for r in rows:                         # в файле Росстата субъекты идут после своего округа
        if r["level"] == "федеральный округ":
            fo = r["region"]
        r["federal_district"] = fo if r["level"] == "субъект" else (r["region"] if r["level"] == "федеральный округ" else "")
        r["guests_per_room"] = round(int(r["guests"]) / int(r["rooms"]), 1)
        r["guests_share_pct"] = round(int(r["guests"]) / int(ru[r["year"]]["guests"]) * 100, 3)
        r["rooms_share_pct"] = round(int(r["rooms"]) / int(ru[r["year"]]["rooms"]) * 100, 3)
        r["date"] = f"{r['year']}-01-01"
        r["source"] = "Росстат, средства размещения по субъектам (S21)"
    write("regions_rooms_guests.csv", rows)

    # 6. Прогноз и стресс-вариант -------------------------------------------------------
    fc = sql_file_table("sql/analysis/forecast_2027.sql", "scenario,fund_2026")
    hist = q("SELECT year, occupancy_label FROM annual_chart ORDER BY year")
    rows = [{"year": h["year"], "scenario": "факт", "occupancy_pct": "63.7" if h["year"] == "2025" else h["occupancy_label"],
             "source": "NF Group S1"} for h in hist]
    for r in fc:
        name = r["scenario"].strip('"')
        rows.append({"year": "2025", "scenario": name, "occupancy_pct": "63.7", "source": "база прогноза"})
        rows.append({"year": "2026", "scenario": name, "occupancy_pct": r["occ_2026"], "source": "forecast_2027.sql"})
        rows.append({"year": "2027", "scenario": name, "occupancy_pct": r["occ_2027"], "source": "forecast_2027.sql"})
    for r in rows:
        r["date"] = f"{r['year']}-01-01"
    write("forecast_occupancy.csv", rows)
    st = sql_file_table("sql/analysis/forecast_2027.sql", "variant,demand_2027_pct")
    rows = [{"step_order": i + 1, "variant": r["variant"].strip('"'), "demand_2027_pct": r["demand_2027_pct"],
             "occupancy_2027_pct": r["occ_2027"], "revpar_2027_change_pct": r["revpar_2027_pct"],
             "source": "forecast_2027.sql, раздел 7"} for i, r in enumerate(st)]
    write("forecast_stress_2027.csv", rows)

    # 7. Качество данных ----------------------------------------------------------------
    rows = list(csv.DictReader(open(ROOT / "data/clean/nf_checks.csv", encoding="utf-8")))
    write("data_quality_checks.csv", rows)
    rows = q("""SELECT metric, period AS year, source_id AS edition, value FROM indicators
                WHERE metric IN ('adr', 'revpar', 'occupancy', 'rooms_total') AND period IN ('2023', '2024')
                ORDER BY metric, period, source_id""")
    names = {"S9": "выпуск за 2023 год", "S3": "выпуск за 2024 год", "S1": "выпуск за 2025 год"}
    for r in rows:
        r["edition_name"] = names[r["edition"]]
        r["metric"] = METRIC_RU[r["metric"]]
    write("data_revisions.csv", rows)


if __name__ == "__main__":
    main()
