-- Точки роста и возможности: сколько каждая стоит и на чём основана.
--
-- Отель-пример — 150 номеров (как в productivity_model.sql); загрузка и цена
-- по месяцам — средние по Петербургу (NF Group, S1). Везде, где есть
-- допущение, оно названо.
--
-- Запуск: duckdb -c ".read sql/setup.sql" -c ".read sql/analysis/opportunities.sql"

CREATE OR REPLACE TEMP VIEW m25 AS
SELECT
    month,
    occupancy_label / 100.0                          AS occ,
    adr_est                                          AS adr,
    DAY(LAST_DAY(MAKE_DATE(2025, month, 1)))         AS days,
    month IN (11, 12, 1, 2, 3)                       AS is_winter
FROM monthly_chart WHERE year = 2025;

-- 1. Где рынок потерял гостей в 2025 г. по сравнению с 2024 г. -------------------
-- Потерянные номеро-ночи = разница в загрузке × номера × дни; оцениваем их по
-- цене 2025 г. Это спрос, который год назад существовал, — в отличие от
-- «зимнего резерва», где гостей нет годами.
CREATE OR REPLACE TEMP VIEW lost AS
SELECT
    a.month,
    b.occupancy_label                         AS occ_2024,
    a.occupancy_label                         AS occ_2025,
    a.occupancy_label - b.occupancy_label     AS occ_change_pp,
    ROUND((a.adr_est / b.adr_est - 1) * 100, 1) AS adr_change_pct,
    150 * DAY(LAST_DAY(MAKE_DATE(2025, a.month, 1)))
        * (b.occupancy_label - a.occupancy_label) / 100.0 * a.adr_est AS lost_rub
FROM monthly_chart a
JOIN monthly_chart b ON b.month = a.month AND b.year = 2024
WHERE a.year = 2025;

SELECT month, occ_2024, occ_2025, occ_change_pp, adr_change_pct,
       ROUND(lost_rub / 1e6, 1) AS lost_mln
FROM lost ORDER BY month;

SELECT
    CASE WHEN month IN (11, 12, 1, 2, 3) THEN 'ноябрь–март'
         WHEN month IN (6, 7, 8)         THEN 'июнь–август'
         ELSE 'апрель–май, сентябрь–октябрь' END   AS season,
    ROUND(SUM(lost_rub) / 1e6, 1)                  AS lost_mln,
    ROUND(SUM(lost_rub) / (SELECT SUM(150 * days * occ * adr) FROM m25) * 100, 1) AS lost_pct_of_year
FROM lost
GROUP BY season
ORDER BY lost_mln DESC;

-- Для контекста: зима структурно слабая. Сколько стоил бы каждый пункт загрузки
-- в ноябре–марте (не цель, а масштаб проблемы).
SELECT
    ROUND(SUM(150 * days * occ * adr) / 1e6, 1)                           AS room_revenue_year_mln,
    ROUND(SUM(150 * days * 0.01 * adr) FILTER (WHERE is_winter) / 1e6, 2) AS plus_1pp_winter_mln
FROM m25;

-- 2. Месяцы, где цена ниже, чем «обычно» при такой загрузке ----------------------
-- Цену каждого месяца делим на среднюю цену его года: так убираем общий рост
-- цен между 2024 и 2025 гг. По 22 месяцам (без июня — ПМЭФ и белые ночи
-- особый месяц) строим линию «относительная цена ~ загрузка». Если месяц
-- заметно ниже линии, отели, возможно, недобирают в цене.
-- Это корреляция на 22 точках, а не доказательство: состав гостей в разные
-- месяцы разный (деловые / туристы), и цену это тоже определяет.
CREATE OR REPLACE TEMP VIEW rel AS
SELECT *, adr_est / AVG(adr_est) OVER (PARTITION BY year) AS adr_rel
FROM monthly_chart;

CREATE OR REPLACE TEMP VIEW fit AS
SELECT
    REGR_SLOPE(adr_rel, occupancy_label)     AS slope,
    REGR_INTERCEPT(adr_rel, occupancy_label) AS intercept,
    REGR_R2(adr_rel, occupancy_label)        AS r2
FROM rel WHERE month <> 6;

SELECT ROUND(slope * 100, 2) AS pct_of_avg_price_per_occ_point, ROUND(r2, 2) AS r2 FROM fit;

-- Месяцы, которые ниже линии в ОБА года, — устойчивый сигнал, а не случайность
SELECT
    r.month,
    MAX(r.occupancy_label) FILTER (WHERE year = 2025)                         AS occ_2025,
    ROUND(MAX((r.adr_rel / (f.intercept + f.slope * r.occupancy_label) - 1) * 100)
          FILTER (WHERE year = 2024))                                         AS vs_line_2024_pct,
    ROUND(MAX((r.adr_rel / (f.intercept + f.slope * r.occupancy_label) - 1) * 100)
          FILTER (WHERE year = 2025))                                         AS vs_line_2025_pct
FROM rel r CROSS JOIN fit f
WHERE r.month <> 6
GROUP BY r.month
ORDER BY vs_line_2025_pct;

-- Размер: в месяцах 2025 г., которые ниже линии больше чем на 5% в оба года,
-- закрыть половину разрыва без потери гостей (оптимистичное допущение).
WITH gap AS (
    SELECT r.year, r.month, r.adr_est, r.occupancy_label,
           -- средняя цена года = adr_est / adr_rel (та же нормировка, что в линии, с июнем)
           (f.intercept + f.slope * r.occupancy_label) * (r.adr_est / r.adr_rel) AS adr_line
    FROM rel r CROSS JOIN fit f
    WHERE r.month <> 6
), both_years AS (
    SELECT month FROM gap GROUP BY month
    HAVING BOOL_AND(adr_est < 0.95 * adr_line)
)
SELECT
    STRING_AGG(g.month::VARCHAR, ', ' ORDER BY g.month)                              AS months,
    ROUND(SUM(150 * m.days * m.occ * 0.5 * (g.adr_line - g.adr_est)) / 1e6, 1)      AS extra_mln,
    ROUND(SUM(150 * m.days * m.occ * 0.5 * (g.adr_line - g.adr_est))
        / (SELECT SUM(150 * days * occ * adr) FROM m25) * 100, 1)                   AS extra_pct_of_year
FROM gap g
JOIN m25 m ON m.month = g.month
WHERE g.year = 2025 AND g.month IN (SELECT month FROM both_years);

-- То же только для марта и апреля (осенние месяцы рискованнее: в ноябре 2025 г.
-- загрузка упала на 4 п. п. при росте цены на 11,5%)
WITH gap AS (
    SELECT r.year, r.month, r.adr_est,
           (f.intercept + f.slope * r.occupancy_label) * (r.adr_est / r.adr_rel) AS adr_line
    FROM rel r CROSS JOIN fit f WHERE r.month IN (3, 4)
)
SELECT ROUND(SUM(150 * m.days * m.occ * 0.5 * (g.adr_line - g.adr_est)) / 1e6, 1) AS extra_mar_apr_mln,
       ROUND(SUM(150 * m.days * m.occ * 0.5 * (g.adr_line - g.adr_est))
           / (SELECT SUM(150 * days * occ * adr) FROM m25) * 100, 1) AS extra_mar_apr_pct
FROM gap g JOIN m25 m ON m.month = g.month WHERE g.year = 2025;

-- 3. Экономсегмент: та же выручка на номер при меньшем повышении цены ----------------
-- IBC (S13): I пол. 2025 — загрузка 61%, цена 3,5 тыс.; I пол. 2026 — 52% и 4,1 тыс.
-- «Наблюдаемая эластичность» = изменение загрузки / изменение цены. Она грубая:
-- в тот же год упал и сам спрос, так что это верхняя оценка чувствительности.
WITH e AS (
    SELECT
        LN(52.0 / 61) / LN(4.1 / 3.5) AS elasticity,   -- дуговая, через логарифмы
        3.5 * 61 / 100.0              AS revpar_2025,
        4.1 * 52 / 100.0              AS revpar_2026
)
SELECT
    ROUND(elasticity, 2)                                                 AS observed_elasticity,
    ROUND(revpar_2026 * 1000)                                            AS revpar_2026_rub,
    p.price_growth_pct,
    ROUND(61 * POW(1 + p.price_growth_pct / 100.0, elasticity), 1)       AS occ_if,
    ROUND(3.5 * (1 + p.price_growth_pct / 100.0)
        * 61 * POW(1 + p.price_growth_pct / 100.0, elasticity) / 100 * 1000) AS revpar_if_rub
FROM e CROSS JOIN (VALUES (0), (4), (8), (12), (17)) p(price_growth_pct)
ORDER BY p.price_growth_pct;

-- 4. Иностранцы: сколько загрузки даёт возврат части потока ----------------------
-- NF (S1): иностранцев в 2025 г. 0,8 млн из 12,4 млн, в 2019 г. — 4,9 млн.
-- Допущение: иностранный турист даёт отелям столько же номеро-ночей, сколько
-- средний турист (скорее занижение: иностранцы реже живут у знакомых).
-- Эластичность загрузки к спросу — 0,6 п. п. на 1% (forecast_2027.sql).
SELECT
    g.foreign_growth_pct,
    ROUND(0.8 * g.foreign_growth_pct / 100, 2)                AS extra_foreign_mln,
    ROUND(0.8 * g.foreign_growth_pct / 100 / 12.4 * 100, 1)    AS demand_add_pct,
    ROUND(0.8 * g.foreign_growth_pct / 100 / 12.4 * 100 * 0.6, 1) AS occ_add_pp
FROM (VALUES (25), (50), (100)) g(foreign_growth_pct);

-- 5. Индекс напряжённости предложения по регионам ---------------------------------
-- «Гостей на номер» в 2025 г. к 2019 г. (Росстат, S21). Растёт — спрос обгоняет
-- номера (кандидат для строительства), падает — номеров избыток.
-- Только регионы, где в 2025 г. было не меньше 0,5 млн гостей.
WITH g AS (
    SELECT region,
        MAX(guests * 1.0 / rooms) FILTER (WHERE year = 2019) AS gpr_2019,
        MAX(guests * 1.0 / rooms) FILTER (WHERE year = 2025) AS gpr_2025,
        MAX(guests) FILTER (WHERE year = 2025)               AS guests_2025,
        MAX(guests) FILTER (WHERE year = 2024)               AS guests_2024
    FROM regions WHERE level = 'субъект'
    GROUP BY region
)
SELECT
    region,
    ROUND(guests_2025 / 1e6, 2)                    AS guests_2025_mln,
    ROUND(gpr_2019)                                AS guests_per_room_2019,
    ROUND(gpr_2025)                                AS guests_per_room_2025,
    ROUND((gpr_2025 / gpr_2019 - 1) * 100)         AS tension_change_pct,
    ROUND((guests_2025 * 1.0 / guests_2024 - 1) * 100, 1) AS guests_2025_pct
FROM g
WHERE guests_2025 >= 500000
ORDER BY tension_change_pct DESC;
