#!/usr/bin/env bash
# Полная пересборка проекта: исходники → таблицы → проверки → страница отчёта.
# Запуск из корня проекта:  bash scripts/run_all.sh
# Нужны: Python 3.12+ с пакетами из requirements.txt в .venv и DuckDB CLI.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python

$PY scripts/download_raw.py          # исходные файлы + контрольные суммы
$PY scripts/extract_nf_indicators.py # таблицы «Основные показатели» NF Group
$PY scripts/extract_nf_openings.py   # открытые отели и апарт-отели
$PY scripts/extract_nf_charts.py     # ряды с графиков NF Group (с самопроверкой)
$PY scripts/extract_ibc.py           # IBC Real Estate / Hotel Advisors
$PY scripts/extract_rosstat.py       # зарплаты и инфляция
$PY scripts/extract_rosstat_regions.py # гости и номера по регионам
$PY scripts/check_nf.py              # сверка цифр NF Group
$PY scripts/build_investigation_html.py # страница report/index.html
$PY scripts/build_bi_datasets.py     # наборы данных для DataLens
echo "Готово."
