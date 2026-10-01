"""Сверка цифр NF Group (S1–S3) после переноса в data/clean/.

Проверки:
  A. Цифры за 2025 год из поисковой выдачи (записаны в SOURCES.md) против таблицы S1.
  B. Внутренняя арифметика каждой таблицы:
     - фонд всего = гостиницы + апарт-отели; ввод всего = ввод гостиниц + ввод апарт-отелей;
     - RevPAR ≈ ADR × загрузка (допуск 0,5%: загрузка в PDF округлена до 0,1 п. п.);
     - напечатанная «Динамика» против пересчитанной (допуск 0,15).
  C. Одни и те же периоды в разных обзорах (2024 в S1 и в S3; конец 2024 и I пол. 2025 в S2).
  D. Сумма номеров в списках открытых объектов против строки «Введено» таблицы.

Результат: data/clean/nf_checks.csv (одна строка = одна проверка) и краткая сводка в консоли.
Статусы: ок — совпало; расхождение — нужно учитывать при анализе.

Запуск:  .venv/bin/python scripts/check_nf.py
"""

import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "data" / "clean"

ind = list(csv.DictReader(open(CLEAN / "nf_key_indicators.csv", encoding="utf-8")))
opn = list(csv.DictReader(open(CLEAN / "nf_openings.csv", encoding="utf-8")))

V = {(r["source_id"], r["period"], r["metric"]): float(r["value"]) for r in ind}
CH = {(r["source_id"], r["period"], r["metric"]): (float(r["change_reported"]), r["change_unit"])
      for r in ind if r["change_reported"]}

checks = []


def add(group, name, expected, actual, tol, note=""):
    diff = actual - expected
    ok = abs(diff) <= tol
    checks.append({"group": group, "check": name, "expected": round(expected, 2),
                   "actual": round(actual, 2), "diff": round(diff, 2),
                   "status": "ок" if ok else "расхождение", "note": note})


# A. Поисковая выдача против PDF (S1, 2025)
search = {"occupancy": 63.7, "adr": 8496, "revpar": 5412}
for m, v in search.items():
    add("A: выдача vs PDF", f"S1 2025 {m}", v, V[("S1", "2025", m)], 0)
add("A: выдача vs PDF", "S1 2025 rooms_total (выдача: 24,9 тыс.)", 24.9,
    round(V[("S1", "2025", "rooms_total")] / 1000, 1), 0)
add("A: выдача vs PDF", "S1 2025 доля апарт-отелей, % (выдача: 37%)", 37,
    round(V[("S1", "2025", "rooms_apart")] / V[("S1", "2025", "rooms_total")] * 100), 0)

# B. Внутренняя арифметика
periods = sorted({(r["source_id"], r["period"]) for r in ind})
for sid, p in periods:
    add("B: арифметика", f"{sid} {p}: фонд = гостиницы + апарт",
        V[(sid, p, "rooms_hotels")] + V[(sid, p, "rooms_apart")], V[(sid, p, "rooms_total")], 0)
    add("B: арифметика", f"{sid} {p}: ввод = гостиницы + апарт",
        V[(sid, p, "new_rooms_hotels")] + V[(sid, p, "new_rooms_apart")],
        V[(sid, p, "new_rooms_total")], 0)
    calc = V[(sid, p, "adr")] * V[(sid, p, "occupancy")] / 100
    add("B: арифметика", f"{sid} {p}: RevPAR = ADR × загрузка", calc,
        V[(sid, p, "revpar")], calc * 0.005)

pairs = {("S1", "2025"): "2024", ("S2", "2025-H1"): "2024-H1", ("S3", "2024"): "2023",
         ("S9", "2023"): "2022"}
for (sid, cur, metric), (reported, unit) in CH.items():
    prev = V[(sid, pairs[(sid, cur)], metric)]
    now = V[(sid, cur, metric)]
    if unit == "п.п.":
        calc = now - prev
    elif unit == "x":
        calc = now / prev
    else:
        calc = (now / prev - 1) * 100
    add("B: арифметика", f"{sid} {cur}: динамика {metric} ({unit})", calc, reported, 0.15,
        "напечатано в PDF vs пересчёт из значений")

# C. Одни и те же периоды в разных обзорах
for metric in ["rooms_total", "rooms_hotels", "rooms_apart", "new_rooms_total",
               "new_rooms_hotels", "new_rooms_apart", "rooms_intl_operators",
               "occupancy", "adr", "revpar"]:
    add("C: между обзорами", f"2024 {metric}: S3 (отчёт за 2024) vs S1 (отчёт за 2025)",
        V[("S3", "2024", metric)], V[("S1", "2024", metric)], 0,
        "значение 2024 г. пересмотрено в следующем отчёте" if V[("S3", "2024", metric)] != V[("S1", "2024", metric)] else "")

# 2023 год в выпуске за 2023 (S9) и в выпуске за 2024 (S3)
for metric in ["rooms_total", "rooms_hotels", "rooms_apart", "occupancy", "adr", "revpar"]:
    a9, a3 = V[("S9", "2023", metric)], V[("S3", "2023", metric)]
    add("C: между обзорами", f"2023 {metric}: S9 (отчёт за 2023) vs S3 (отчёт за 2024)", a9, a3, 0,
        "значение 2023 г. пересмотрено в следующем отчёте" if a9 != a3 else "")

# Фонд гостиниц на конец 2024 в S1 и на 30.06.2025 в S2 (в I пол. 2025 ввода гостиниц не было)
add("C: между обзорами", "фонд гостиниц: S1 конец 2024 vs S2 конец I пол. 2025 (ввода не было)",
    V[("S1", "2024", "rooms_hotels")], V[("S2", "2025-H1", "rooms_hotels")], 0)
# Баланс фонда: конец 2024 + ввод 2025 = конец 2025?
BALANCE_NOTES = {
    "rooms_hotels": "−89 = закрытие «Талион Империал Отель» (89 ном., ноябрь 2025, S1 с. 3)",
    "rooms_apart": "причина −97 в отчёте не указана",
    "rooms_total": "−89 гостиницы и −97 апарт-отели",
}
for metric, intake in [("rooms_hotels", "new_rooms_hotels"), ("rooms_apart", "new_rooms_apart"),
                       ("rooms_total", "new_rooms_total")]:
    add("C: между обзорами", f"S1: {metric} 2024 + ввод 2025 vs {metric} 2025",
        V[("S1", "2024", metric)] + V[("S1", "2025", intake)], V[("S1", "2025", metric)], 0,
        BALANCE_NOTES[metric])

# D. Списки открытых объектов против строки «Введено»
sums = defaultdict(int)
for r in opn:
    key = (r["source_id"], r["period"], "new_rooms_hotels" if r["format"] == "Гостиница" else "new_rooms_apart")
    sums[key] += int(r["rooms"])
LIST_NOTES = {
    ("S3", "2024"): "в отчёте приведены только наиболее значимые апарт-отели (7 из 13)",
    ("S1", "2025"): "«Культ Отважных» (72 ном.) есть в S2, но нет в годовом списке S1",
    ("S2", "2025-H1"): "Ladozhsky Avenir и Vertical Club — 0 ном., ещё на классификации",
}
for key, total in sorted(sums.items()):
    add("D: списки объектов", f"{key[0]} {key[1]}: сумма по списку vs {key[2]}",
        V[key], total, 0,
        LIST_NOTES.get(key[:2], ""))

with open(CLEAN / "nf_checks.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(checks[0]))
    w.writeheader()
    w.writerows(checks)

bad = [c for c in checks if c["status"] != "ок"]
print(f"Проверок: {len(checks)}, расхождений: {len(bad)}")
for c in bad:
    print(f"  [{c['group']}] {c['check']}: ждали {c['expected']}, есть {c['actual']} "
          f"(разница {c['diff']}) {c['note']}")
