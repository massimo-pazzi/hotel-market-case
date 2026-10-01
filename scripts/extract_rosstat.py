"""Зарплаты и инфляция из таблиц Росстата (S15–S17) в один CSV по годам.

Файлы скачаны с rosstat.gov.ru 2026-09-30 и лежат в data/raw/ без изменений:
  S15 — tab3-zpl-2025.xlsx: среднемесячная номинальная начисленная зарплата по
        полному кругу организаций по видам деятельности (ОКВЭД2), Россия, 2017–2025.
        Берём «Всего» и «деятельность гостиниц и предприятий общественного питания».
        По Петербургу отдельно по отраслям в этих таблицах данных нет —
        гостиничная зарплата только по России и только вместе с общепитом.
  S16 — tab4-zpl-2025.xlsx, лист «с 2018»: та же зарплата по всей экономике
        по субъектам. Берём Россию и Петербург.
  S17 — ipc_s_1992-2025.xlsx: индекс потребительских цен, декабрь к декабрю
        предыдущего года, %, по субъектам. Берём Россию и Петербург.

Годы в заголовках иногда записаны со сноской («20221)» = 2022 + сноска 1) —
скрипт берёт первые четыре цифры.

Запуск:  .venv/bin/python scripts/extract_rosstat.py
"""

import csv
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "clean" / "rosstat_wages_cpi.csv"
YEARS = range(2018, 2026)


def sheet_rows(fname, sheet):
    wb = openpyxl.load_workbook(RAW / fname, read_only=True, data_only=True)
    return list(wb[sheet].iter_rows(values_only=True))


def year_header(rows):
    """Находит строку с годами и возвращает {год: номер колонки}."""
    for r in rows:
        years = {}
        for i, c in enumerate(r):
            t = str(c).strip() if c is not None else ""
            if len(t) >= 4 and t[:4].isdigit() and 1990 <= int(t[:4]) <= 2030:
                years[int(t[:4])] = i
        if len(years) >= 5:
            return years
    raise ValueError("не нашёл строку с годами")


def row_values(rows, label_start):
    cols = year_header(rows)
    row = next(r for r in rows if r and r[0] and str(r[0]).strip().startswith(label_start))
    return {y: float(row[cols[y]]) for y in YEARS if y in cols and row[cols[y]] not in (None, "")}


def main():
    s15 = sheet_rows("S15_Rosstat_wages_by_OKVED_RF_2017-2025.xlsx", "с 2017 г.")
    s16 = sheet_rows("S16_Rosstat_wages_by_region_2000-2025.xlsx", "с 2018")
    s17 = sheet_rows("S17_Rosstat_CPI_by_region_1992-2025.xlsx", "Лист1")

    series = {
        "wage_ru_all": row_values(s15, "Всего"),
        "wage_ru_hotels_catering": row_values(s15, "деятельность гостиниц и предприятий общественного питания"),
        "wage_spb_all": row_values(s16, "г.Санкт-Петербург"),
        "cpi_ru_dec_dec": row_values(s17, "Российская Федерация"),
        "cpi_spb_dec_dec": row_values(s17, "г.Санкт-Петербург"),
    }
    # Проверка: «Всего» по России в S15 и S16 — одна и та же величина
    s16_ru = row_values(s16, "Российская Федерация")
    for y in YEARS:
        assert abs(series["wage_ru_all"][y] - s16_ru[y]) < 1, f"S15 и S16 расходятся в {y}"

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year"] + list(series))
        for y in YEARS:
            w.writerow([y] + [series[k].get(y) for k in series])
    print(f"{OUT.relative_to(ROOT)}: {len(YEARS)} лет; проверка S15 = S16 по России пройдена")


if __name__ == "__main__":
    main()
