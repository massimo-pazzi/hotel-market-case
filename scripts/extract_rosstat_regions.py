"""Число номеров и размещённых лиц в средствах размещения по регионам (Росстат, S21).

Файл SR_god_sub_2025.xlsx (rosstat.gov.ru, раздел «Туризм», обновлён 24.04.2026),
скачан 2026-10-01 в data/raw/ без изменений. Листы:
  «2» — число номеров в средствах размещения, на конец года;
  «6» — численность размещённых лиц за год.
Строки — Россия, федеральные округа и субъекты; колонки — 2002–2025.

Что делает скрипт:
  * берёт 2015–2025 гг. (годы в заголовке бывают со звёздочкой: «2022 *» —
    без новых регионов; звёздочку убирает);
  * значения по округам в файле частично записаны формулами — читает
    сохранённые Excel-ом результаты (data_only=True);
  * помечает уровень строки: страна / федеральный округ / субъект;
  * пишет data/clean/rosstat_regions_rooms_guests.csv в длинном формате.

Оговорка: в середине 2010-х Росстат расширял охват средств размещения
(например, в Петербурге номеров стало в 2,8 раза больше за 2015–2025 гг.),
поэтому абсолютный рост по годам сравнивать осторожно; доли регионов в
общероссийском итоге — надёжнее.

Запуск:  .venv/bin/python scripts/extract_rosstat_regions.py
"""

import csv
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "raw" / "S21_Rosstat_accommodation_by_region_2002-2025.xlsx"
OUT = ROOT / "data" / "clean" / "rosstat_regions_rooms_guests.csv"
YEARS = range(2015, 2026)


def read_sheet(ws):
    rows = list(ws.iter_rows(values_only=True))
    header = next(r for r in rows if r and r[0] is None and any(str(c).startswith("2002") for c in r if c))
    col = {}
    for i, c in enumerate(header):
        if c is not None and str(c).strip()[:4].isdigit():
            col[int(str(c).strip()[:4])] = i
    data = {}
    for r in rows:
        name = str(r[0]).strip() if r and r[0] else ""
        if not name or name.startswith(("*", "1 ", "К содержанию")) or name.lower() == "человек":
            continue
        vals = {y: r[col[y]] for y in YEARS if y in col}
        if all(isinstance(v, (int, float)) for v in vals.values()):
            data[name] = vals
    return data


def level(name):
    if name == "Российская Федерация":
        return "страна"
    if "федеральный округ" in name:
        return "федеральный округ"
    return "субъект"


def main():
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    rooms, guests = read_sheet(wb["2"]), read_sheet(wb["6"])
    names = [n for n in guests if n in rooms]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["region", "level", "year", "rooms", "guests"])
        for n in names:
            for y in YEARS:
                w.writerow([n, level(n), y, int(rooms[n][y]), int(guests[n][y])])
    # Проверка: сумма округов = России (по размещённым лицам)
    fo = [n for n in names if level(n) == "федеральный округ"]
    for y in (2019, 2025):
        s = sum(guests[n][y] for n in fo)
        ru = guests["Российская Федерация"][y]
        print(f"  {y}: сумма {len(fo)} округов = {s:,.0f}, Россия = {ru:,.0f}, расхождение {s / ru - 1:+.2%}")
    print(f"{OUT.relative_to(ROOT)}: {len(names)} строк-регионов × {len(YEARS)} лет")


if __name__ == "__main__":
    main()
