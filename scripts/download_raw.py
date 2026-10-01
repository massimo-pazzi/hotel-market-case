"""Скачивает исходные файлы в data/raw/ по манифесту и проверяет контрольные суммы.

Манифест — data/raw_manifest.csv: файл, ссылка, SHA-256, лежит ли файл в
репозитории. Таблицы Росстата (открытые данные) лежат в репозитории; отчёты
NF Group и IBC Real Estate — нет: это публикации компаний, поэтому в
репозитории только ссылки на них.

Если сумма скачанного файла не совпадает с манифестом, издатель заменил
файл — расчёты могут измениться. Скрипт сообщает об этом и не перезаписывает
манифест.

Запуск:  .venv/bin/python scripts/download_raw.py
"""

import csv
import hashlib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
MANIFEST = ROOT / "data" / "raw_manifest.csv"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    problems = 0
    for row in csv.DictReader(open(MANIFEST, encoding="utf-8")):
        path = RAW / row["file"]
        if not path.exists():
            print(f"  скачиваю {row['file']} …")
            req = urllib.request.Request(row["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                path.write_bytes(r.read())
        ok = sha256(path) == row["sha256"]
        problems += not ok
        print(f"{'ок ' if ok else 'НЕ СОВПАДАЕТ'}  {row['file']}")
    if problems:
        print(f"\nФайлов с другой контрольной суммой: {problems}. Издатель мог обновить файл — "
              "сверьте результаты скриптов с data/clean/ из репозитория.")
    else:
        print("\nВсе исходные файлы на месте и совпадают с манифестом.")


if __name__ == "__main__":
    main()
