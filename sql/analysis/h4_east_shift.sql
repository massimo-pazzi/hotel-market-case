-- H4. Смещается ли спрос на размещение на восток, и теряет ли Петербург долю?
--
-- Гипотеза (из публикаций о «развороте экономики на восток»): деловая
-- активность и спрос на гостиницы смещаются на Урал, в Сибирь и на Дальний
-- Восток; в Новосибирске не хватает гостиниц.
--
-- Данные: Росстат (S21), число размещённых лиц и номеров в средствах
-- размещения по регионам, 2015–2025. Это ВСЕ гости (отдых, дела, лечение),
-- не только деловые, и все средства размещения, не только отели.
-- Росстат в 2010-х расширял охват, поэтому смотрим ДОЛИ регионов в
-- общероссийском итоге (они к этому устойчивее) и в основном с 2019 г.
-- 2020–2021 гг. — ковид.
--
-- Запуск: duckdb -c ".read sql/setup.sql" -c ".read sql/analysis/h4_east_shift.sql"

CREATE OR REPLACE TEMP VIEW shares AS
SELECT
    r.region, r.level, r.year, r.guests, r.rooms,
    r.guests * 100.0 / ru.guests AS guests_share_pct,
    r.rooms  * 100.0 / ru.rooms  AS rooms_share_pct,
    r.guests * 1.0 / r.rooms     AS guests_per_room
FROM regions r
JOIN regions ru ON ru.year = r.year AND ru.level = 'страна';

-- 1. Федеральные округа: доля в числе гостей России ----------------------------
SELECT
    region,
    ROUND(MAX(guests_share_pct) FILTER (WHERE year = 2015), 1) AS share_2015,
    ROUND(MAX(guests_share_pct) FILTER (WHERE year = 2019), 1) AS share_2019,
    ROUND(MAX(guests_share_pct) FILTER (WHERE year = 2025), 1) AS share_2025,
    ROUND(MAX(guests_share_pct) FILTER (WHERE year = 2025)
        - MAX(guests_share_pct) FILTER (WHERE year = 2019), 2)  AS change_2019_2025_pp,
    ROUND((MAX(guests) FILTER (WHERE year = 2025) * 1.0
        / MAX(guests) FILTER (WHERE year = 2019) - 1) * 100)    AS guests_growth_2019_2025_pct
FROM shares
WHERE level = 'федеральный округ'
GROUP BY region
ORDER BY change_2019_2025_pp DESC;

-- 2. Крупнейшие направления: доля, рост и «гостей на номер» ----------------------
-- «Гостей на номер» — сколько человек за год приходится на один номер. Если
-- показатель растёт, спрос обгоняет предложение (номеров «не хватает»);
-- если падает — предложение обгоняет спрос. Зависит и от длительности
-- проживания, поэтому это грубый индикатор.
SELECT
    region,
    ROUND(MAX(guests_share_pct) FILTER (WHERE year = 2019), 2) AS share_2019,
    ROUND(MAX(guests_share_pct) FILTER (WHERE year = 2025), 2) AS share_2025,
    ROUND((MAX(guests) FILTER (WHERE year = 2025) * 1.0
        / MAX(guests) FILTER (WHERE year = 2019) - 1) * 100)    AS guests_2019_2025_pct,
    ROUND((MAX(guests) FILTER (WHERE year = 2025) * 1.0
        / MAX(guests) FILTER (WHERE year = 2024) - 1) * 100, 1) AS guests_2025_pct,
    ROUND(MAX(guests_per_room) FILTER (WHERE year = 2019))      AS guests_per_room_2019,
    ROUND(MAX(guests_per_room) FILTER (WHERE year = 2025))      AS guests_per_room_2025
FROM shares
WHERE region IN ('Российская Федерация', 'г.Москва', 'г.Санкт-Петербург',
                 'Новосибирская область', 'Свердловская область', 'Республика Татарстан',
                 'Приморский край', 'Краснодарский край', 'Московская область',
                 'Тюменская область', 'Челябинская область', 'Иркутская область')
GROUP BY region
ORDER BY share_2025 DESC;

-- 3. Доля Петербурга по годам -----------------------------------------------------
SELECT year,
       ROUND(guests_share_pct, 2) AS spb_guests_share_pct,
       ROUND(rooms_share_pct, 2)  AS spb_rooms_share_pct
FROM shares
WHERE region = 'г.Санкт-Петербург'
ORDER BY year;
