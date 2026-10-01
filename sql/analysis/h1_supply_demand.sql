-- H1. Спрос и предложение: растёт ли фонд быстрее спроса и давит ли это на загрузку?
--
-- Запуск (из корня проекта):
--   duckdb -c ".read sql/setup.sql" -c ".read sql/analysis/h1_supply_demand.sql"
--
-- Данные (все — из одного отчёта S1, чтобы методика была единой):
--   supply_chart  — фонд на начало года (оценка по графику) и ввод за год (подпись)
--   tourist_flow  — турпоток, млн чел. (подписи графика; первоисточник — Комитет по туризму)
--   annual_chart  — ADR, RevPAR (оценка по графику), загрузка (подпись, целые %)
--
-- Допущения:
--   * Средний фонд за год = фонд на начало + половина ввода (объекты открываются
--     в течение года). Это стандартное приближение, точных дат открытия нет.
--   * Проданные номеро-ночи = средний фонд × 365 × загрузка. Загрузка округлена
--     до целого %, поэтому ошибка — до ±0,8% от значения.
--   * 2020–2021 — ковид; сравнения строим от 2019 (последний «нормальный» год)
--     и от 2023 (рынок восстановился).

-- 1. Годовая сводка -----------------------------------------------------------
CREATE OR REPLACE TEMP VIEW h1_year AS
WITH fund AS (
    SELECT
        year,
        SUM(start_rooms_est)                          AS rooms_start,
        SUM(intake_label)                             AS rooms_intake,
        SUM(start_rooms_est + intake_label / 2.0)     AS rooms_avg,
        SUM(CASE WHEN segment = 'apart' THEN start_rooms_est + intake_label / 2.0 END)
            / SUM(start_rooms_est + intake_label / 2.0) AS apart_share
    FROM supply_chart
    WHERE is_forecast = 0
    GROUP BY year
)
SELECT
    f.year,
    ROUND(f.rooms_avg)                                         AS rooms_avg,
    ROUND(f.apart_share * 100, 1)                              AS apart_share_pct,
    t.total_mln                                                AS tourists_mln,
    a.occupancy_label                                          AS occ_pct,
    a.adr_est                                                  AS adr,
    a.revpar_est                                               AS revpar,
    ROUND(f.rooms_avg * 365 * a.occupancy_label / 100 / 1e6, 2) AS room_nights_sold_mln,
    -- сколько туристов приходится на один номер в среднем за год
    ROUND(t.total_mln * 1e6 / f.rooms_avg)                     AS tourists_per_room
FROM fund f
JOIN tourist_flow t USING (year)
JOIN annual_chart a USING (year)
ORDER BY f.year;

SELECT * FROM h1_year;

-- 2. Годовой рост (г/г, %) ------------------------------------------------------
-- LAG берёт значение из предыдущей строки (предыдущего года).
SELECT
    year,
    ROUND((rooms_avg / LAG(rooms_avg) OVER w - 1) * 100, 1)                      AS rooms_growth,
    ROUND((tourists_mln / LAG(tourists_mln) OVER w - 1) * 100, 1)                AS tourists_growth,
    ROUND((room_nights_sold_mln / LAG(room_nights_sold_mln) OVER w - 1) * 100, 1) AS sold_growth,
    occ_pct - LAG(occ_pct) OVER w                                                 AS occ_change_pp,
    ROUND((adr / LAG(adr) OVER w - 1) * 100, 1)                                  AS adr_growth,
    ROUND((revpar / LAG(revpar) OVER w - 1) * 100, 1)                            AS revpar_growth
FROM h1_year
WINDOW w AS (ORDER BY year)
ORDER BY year;

-- 3. Накопленный рост за периоды (среднегодовой, CAGR, %) ------------------------
-- CAGR = (конец / начало)^(1 / число лет) − 1
WITH p AS (
    SELECT * FROM (VALUES (2016, 2019, '2016→2019 до ковида'),
                          (2019, 2025, '2019→2025 от доковидного'),
                          (2023, 2025, '2023→2025 после восстановления')) v(y0, y1, label)
)
SELECT
    p.label,
    ROUND((POW(e.rooms_avg / s.rooms_avg, 1.0 / (p.y1 - p.y0)) - 1) * 100, 1)       AS rooms_cagr,
    ROUND((POW(e.tourists_mln / s.tourists_mln, 1.0 / (p.y1 - p.y0)) - 1) * 100, 1) AS tourists_cagr,
    ROUND((POW(e.room_nights_sold_mln / s.room_nights_sold_mln, 1.0 / (p.y1 - p.y0)) - 1) * 100, 1) AS sold_cagr,
    ROUND((POW(e.adr / s.adr, 1.0 / (p.y1 - p.y0)) - 1) * 100, 1)                   AS adr_cagr,
    e.occ_pct - s.occ_pct                                                           AS occ_change_pp
FROM p
JOIN h1_year s ON s.year = p.y0
JOIN h1_year e ON e.year = p.y1
ORDER BY p.y0;

-- 4. Когда в 2025 г. началось падение загрузки? Помесячно 2025 против 2024 ------
-- Таблица S2: за I пол. загрузка не изменилась (60,9% против 60,8%), а за год
-- упала на 1,9 п. п. Значит, спад — во II полугодии. Проверяем по месяцам.
-- ADR помесячно — оценка по графику S1; RevPAR считаем как ADR × загрузка.
CREATE OR REPLACE TEMP VIEW h1_month AS
SELECT
    m.month,
    CASE WHEN m.month <= 6 THEN 'I пол.' ELSE 'II пол.' END AS half,
    p.occupancy_label                          AS occ_2024,
    m.occupancy_label                          AS occ_2025,
    m.occupancy_label - p.occupancy_label      AS occ_change_pp,
    ROUND((m.adr_est / p.adr_est - 1) * 100, 1) AS adr_growth,
    ROUND((m.adr_est * m.occupancy_label / (p.adr_est * p.occupancy_label) - 1) * 100, 1)
                                               AS revpar_growth
FROM monthly_chart m
JOIN monthly_chart p ON p.month = m.month AND p.year = 2024
WHERE m.year = 2025
ORDER BY m.month;

SELECT * FROM h1_month;

-- Итог по полугодиям (простое среднее месяцев: дни в месяцах почти равны,
-- для оценки направления этого достаточно)
SELECT
    half,
    ROUND(AVG(occ_change_pp), 1)  AS avg_occ_change_pp,
    ROUND(AVG(adr_growth), 1)     AS avg_adr_growth,
    ROUND(AVG(revpar_growth), 1)  AS avg_revpar_growth
FROM h1_month
GROUP BY half
ORDER BY half;
