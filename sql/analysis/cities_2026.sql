-- Петербург на фоне других городов, I полугодие 2026 г.
--
-- Вопрос: замедление в Петербурге — местная история (избыток номеров, уход
-- гостей в квартиры) или общероссийская (остывание экономики)?
--
-- Данные (все — IBC Real Estate, «Гостиничная недвижимость, II кв. 2026», S13):
--   ibc_city_revpar — изменение RevPAR за I пол. 2026 г/г по 26 локациям (Hotel Advisors);
--   ibc_placed      — число размещённых лиц, январь–май 2026, топ-20 регионов (Росстат);
--   ibc_segments    — загрузка и ADR по ценовым сегментам, Петербург и Москва.
--
-- Запуск: duckdb -c ".read sql/setup.sql" -c ".read sql/analysis/cities_2026.sql"

-- 1. Где Петербург среди 26 локаций по изменению RevPAR ------------------------
SELECT
    COUNT(*)                                                 AS locations,
    MEDIAN(revpar_change_pct)                                AS median_change,
    COUNT(*) FILTER (WHERE revpar_change_pct < 0)            AS locations_falling,
    MAX(revpar_change_pct) FILTER (WHERE location = 'Санкт-Петербург') AS spb_change,
    COUNT(*) FILTER (WHERE revpar_change_pct >
        (SELECT revpar_change_pct FROM ibc_city_revpar WHERE location = 'Санкт-Петербург'))
                                                             AS locations_better_than_spb
FROM ibc_city_revpar;
-- Оговорка: IBC приводит локации как «примеры» групп, это не полный список
-- городов России. Медиана — по этим 26 примерам.

-- 2. Спрос (Росстат) против выручки на номер (Hotel Advisors) ---------------------
-- Регион Росстата сопоставляем с городом из выборки Hotel Advisors вручную:
-- гостиницы региона в основном сосредоточены в его столице. Это допущение.
WITH map(region, location) AS (
    VALUES ('Москва', 'Москва'),
           ('Санкт-Петербург', 'Санкт-Петербург'),
           ('Московская область', 'Московская обл.'),
           ('Ленинградская область', 'Ленинградская обл.'),
           ('Республика Татарстан', 'Казань'),
           ('Свердловская область', 'Екатеринбург'),
           ('Новосибирская область', 'Новосибирск'),
           ('Самарская область', 'Самара'),
           ('Нижегородская область', 'Нижний Новгород'),
           ('Иркутская область', 'Иркутск'),
           ('Приморский край', 'Владивосток'),
           ('Тюменская область', 'Тюмень')
)
SELECT
    m.region,
    p.placed_mln,
    p.change_pct            AS guests_change_pct,
    c.revpar_change_pct,
    c.ibc_group
FROM map m
JOIN ibc_placed p      ON p.region = m.region
JOIN ibc_city_revpar c ON c.location = m.location
ORDER BY p.placed_mln DESC;

-- Для контекста: Россия в целом
SELECT placed_mln, change_pct FROM ibc_placed WHERE region = 'Россия';

-- 3. Две стратегии: Петербург и Москва по сегментам ------------------------------
-- RevPAR сегмента = ADR × загрузка (в отчёте по сегментам его нет).
WITH s AS (
    SELECT
        city, segment,
        MAX(CASE WHEN period = '2025-H1' THEN occupancy_pct END)    AS occ25,
        MAX(CASE WHEN period = '2026-H1' THEN occupancy_pct END)    AS occ26,
        MAX(CASE WHEN period = '2025-H1' THEN adr_thousand_rub END) AS adr25,
        MAX(CASE WHEN period = '2026-H1' THEN adr_thousand_rub END) AS adr26
    FROM ibc_segments
    GROUP BY city, segment
)
SELECT
    segment,
    MAX(CASE WHEN city = 'Санкт-Петербург' THEN occ26 - occ25 END)                       AS spb_occ_pp,
    MAX(CASE WHEN city = 'Санкт-Петербург' THEN ROUND((adr26 / adr25 - 1) * 100) END)     AS spb_adr_pct,
    MAX(CASE WHEN city = 'Санкт-Петербург' THEN ROUND((adr26 * occ26 / (adr25 * occ25) - 1) * 100) END) AS spb_revpar_pct,
    MAX(CASE WHEN city = 'Москва' THEN occ26 - occ25 END)                                AS msk_occ_pp,
    MAX(CASE WHEN city = 'Москва' THEN ROUND((adr26 / adr25 - 1) * 100) END)              AS msk_adr_pct,
    MAX(CASE WHEN city = 'Москва' THEN ROUND((adr26 * occ26 / (adr25 * occ25) - 1) * 100) END) AS msk_revpar_pct
FROM s
GROUP BY segment
ORDER BY MIN(adr25);
