-- Цена номера против инфляции и зарплат, 2019–2025.
--
-- Вопрос: растёт ли цена номера в реальном выражении и успевает ли выручка
-- отелей за их главной статьёй затрат — оплатой труда?
--
-- Данные:
--   annual_chart — ADR и RevPAR качественных отелей Петербурга (NF Group, S1;
--                  оценка по графику, отклонение от таблицы ≤0,5%);
--   rosstat      — ИПЦ Петербурга (декабрь к декабрю), зарплата в «деятельности
--                  гостиниц и предприятий общественного питания» по России,
--                  зарплата по всей экономике Петербурга (Росстат, S15–S17).
--
-- Допущения и оговорки:
--   * Зарплата в гостиницах есть только по России и только вместе с общепитом.
--     Отдельно по Петербургу Росстат её в этих таблицах не даёт. Используем как
--     индикатор того, как быстро дорожает труд в отрасли.
--   * ИПЦ — декабрь к декабрю, а ADR — среднее за год. Для многолетнего сравнения
--     расхождение небольшое, для отдельного года — заметное.
--
-- Запуск: duckdb -c ".read sql/setup.sql" -c ".read sql/analysis/costs_wages.sql"

-- 1. Индексы (2019 = 100) и реальная цена номера ---------------------------------
CREATE OR REPLACE TEMP VIEW idx AS
WITH base AS (
    SELECT
        a.year,
        a.adr_est, a.revpar_est,
        r.wage_ru_hotels_catering, r.wage_spb_all, r.cpi_spb_dec_dec,
        -- накопленный уровень цен: произведение годовых индексов, начиная с 2020
        EXP(SUM(CASE WHEN a.year > 2019 THEN LN(r.cpi_spb_dec_dec / 100) ELSE 0 END)
            OVER (ORDER BY a.year)) AS price_level
    FROM annual_chart a
    JOIN rosstat r USING (year)
    WHERE a.year >= 2019
)
SELECT
    year,
    ROUND(price_level * 100)                                              AS cpi_spb_idx,
    ROUND(adr_est / FIRST(adr_est) OVER w * 100)                          AS adr_idx,
    ROUND(revpar_est / FIRST(revpar_est) OVER w * 100)                    AS revpar_idx,
    ROUND(wage_ru_hotels_catering / FIRST(wage_ru_hotels_catering) OVER w * 100) AS wage_hotels_idx,
    ROUND(wage_spb_all / FIRST(wage_spb_all) OVER w * 100)                AS wage_spb_idx,
    -- реальная цена номера в рублях 2019 года
    ROUND(adr_est / price_level)                                          AS adr_real_2019rub,
    -- сколько ночей в номере «стоит» месячная зарплата в отрасли
    ROUND(wage_ru_hotels_catering / revpar_est, 1)                        AS wage_in_revpar_days
FROM base
WINDOW w AS (ORDER BY year)
ORDER BY year;

SELECT * FROM idx;

-- 2. Среднегодовые темпы за 2019→2025 и за последний год ---------------------------
SELECT
    '2019→2025, % в год' AS period,
    ROUND((POW(MAX(cpi_spb_idx) FILTER (WHERE year = 2025) / 100, 1 / 6.0) - 1) * 100, 1)     AS cpi,
    ROUND((POW(MAX(adr_idx) FILTER (WHERE year = 2025) / 100, 1 / 6.0) - 1) * 100, 1)         AS adr,
    ROUND((POW(MAX(revpar_idx) FILTER (WHERE year = 2025) / 100, 1 / 6.0) - 1) * 100, 1)      AS revpar,
    ROUND((POW(MAX(wage_hotels_idx) FILTER (WHERE year = 2025) / 100, 1 / 6.0) - 1) * 100, 1) AS wage_hotels
FROM idx
UNION ALL
SELECT
    '2025 к 2024, %',
    ROUND((MAX(cpi_spb_idx) FILTER (WHERE year = 2025) / MAX(cpi_spb_idx) FILTER (WHERE year = 2024) - 1) * 100, 1),
    ROUND((MAX(adr_idx) FILTER (WHERE year = 2025) / MAX(adr_idx) FILTER (WHERE year = 2024) - 1) * 100, 1),
    ROUND((MAX(revpar_idx) FILTER (WHERE year = 2025) / MAX(revpar_idx) FILTER (WHERE year = 2024) - 1) * 100, 1),
    ROUND((MAX(wage_hotels_idx) FILTER (WHERE year = 2025) / MAX(wage_hotels_idx) FILTER (WHERE year = 2024) - 1) * 100, 1)
FROM idx;
