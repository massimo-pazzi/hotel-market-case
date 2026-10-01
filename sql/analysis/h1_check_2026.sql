-- Проверка вывода H1 на данных 2026 года (IBC Real Estate / Hotel Advisors).
--
-- Вывод H1, сделанный по данным NF Group: во II пол. 2025 г. рост цен перестал
-- компенсировать падение загрузки. Если вывод верен, в I пол. 2026 г. должно
-- быть видно продолжение: загрузка ниже прошлого года, рост ADR замедлился,
-- RevPAR не растёт.
--
-- Выборка IBC — классические отели 3–5* от 100 номеров, без апарт-отелей.
-- Уровни с NF Group не сравниваем, сравниваем направление и темпы.
--
-- Запуск: duckdb -c ".read sql/setup.sql" -c ".read sql/analysis/h1_check_2026.sql"

-- 1. Сегменты: изменение загрузки (п. п.) и ADR (%) за два года подряд.
--    RevPAR сегмента считаем как ADR × загрузка (в отчёте по сегментам его нет).
WITH s AS (
    SELECT
        segment,
        MAX(CASE WHEN period = '2024-H1' THEN occupancy_pct END)     AS occ24,
        MAX(CASE WHEN period = '2025-H1' THEN occupancy_pct END)     AS occ25,
        MAX(CASE WHEN period = '2026-H1' THEN occupancy_pct END)     AS occ26,
        MAX(CASE WHEN period = '2024-H1' THEN adr_thousand_rub END)  AS adr24,
        MAX(CASE WHEN period = '2025-H1' THEN adr_thousand_rub END)  AS adr25,
        MAX(CASE WHEN period = '2026-H1' THEN adr_thousand_rub END)  AS adr26
    FROM ibc_segments
    WHERE city = 'Санкт-Петербург'
    GROUP BY segment
)
SELECT
    segment,
    occ25 - occ24                                           AS occ_pp_2025,
    occ26 - occ25                                           AS occ_pp_2026,
    ROUND((adr25 / adr24 - 1) * 100)                        AS adr_pct_2025,
    ROUND((adr26 / adr25 - 1) * 100)                        AS adr_pct_2026,
    ROUND((adr25 * occ25 / (adr24 * occ24) - 1) * 100)      AS revpar_pct_2025,
    ROUND((adr26 * occ26 / (adr25 * occ25) - 1) * 100)      AS revpar_pct_2026
FROM s
ORDER BY adr24;

-- 2. Грубая оценка II пол. 2025 г. по IBC: если год ≈ среднее двух полугодий,
--    то загрузка II пол. ≈ 2 × годовая − I пол. Полугодия не равны по числу
--    ночей и загрузка округлена, поэтому это оценка направления (±2 п. п.).
WITH y AS (
    SELECT
        MAX(CASE WHEN period = '2024' AND metric = 'occupancy' THEN value END) AS occ_y24,
        MAX(CASE WHEN period = '2025' AND metric = 'occupancy' THEN value END) AS occ_y25
    FROM ibc_annual
), h AS (
    SELECT
        MAX(CASE WHEN period = '2024-H1' THEN occupancy_pct END) AS occ_h24,
        MAX(CASE WHEN period = '2025-H1' THEN occupancy_pct END) AS occ_h25
    FROM ibc_segments
    WHERE segment = 'Рынок в целом' AND city = 'Санкт-Петербург'
)
SELECT
    occ_h25 - occ_h24                                   AS h1_2025_change_pp,
    (2 * occ_y25 - occ_h25) - (2 * occ_y24 - occ_h24)   AS h2_2025_change_pp_est
FROM y, h;
