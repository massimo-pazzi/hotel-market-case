-- Модель производительности: сколько стоит труд на проданный номер и что дают
-- четыре рычага экономии. Отель-пример — 150 номеров, загрузка и цена по
-- месяцам 2025 г. — средние по рынку Петербурга (NF Group, S1, с. 7).
--
-- Главные результаты не зависят от размера отеля: затраты считаются
-- на один проданный номер и в процентах от выручки номерного фонда.
--
-- Это МОДЕЛЬ НА ДОПУЩЕНИЯХ, а не измерение. Все допущения — в таблице ниже,
-- с источником. Три сценария: «осторожный» даёт меньшую экономию,
-- «смелый» — большую.
--
-- Запуск: duckdb -c ".read sql/setup.sql" -c ".read sql/analysis/productivity_model.sql"

-- 0. Допущения --------------------------------------------------------------------
-- Источники:
--  [N1] Контур.Отель, «Стандарты уборки номерного фонда»: текущая уборка 15–24 мин,
--       выездная 25–30 мин, 12–16 номеров за 8-часовую смену.
--  [N2] Отраслевые обзоры (hotelmanagement.net, hospitality.institute): выездная
--       20–45 мин, текущая 15–25 мин; хронометраж 60 номеров — 43 и 23 мин.
--  [W1] Росстат (S15): зарплата в гостиницах и общепите по России — 66,1 тыс. ₽ (2025);
--       по всей экономике Петербург выше России в 1,21 раза (S16).
--  [W2] Вакансии горничных на hh.ru, Петербург, 2026: чаще всего 45–70 тыс. ₽.
--  [T1] Страховые взносы работодателя — 30% (общий тариф в пределах базы).
--  [A1] Оценка автора (М. Поципух) по проекту автоматизации ресепшена: заселение
--       на стойке в часы пик 8–15 мин, через киоск 2–3 мин, киоском пользуются
--       30–50% гостей. Опирается на открытые исследования, которые не сохранились;
--       внедрение не проводилось.
--  [D1] Допущение: средняя длительность проживания 2,5 ночи (2–3). Своих данных
--       нет — проверить по Росстату (ночёвки / размещённые лица).
--  [D2] Допущение: 80% оплаченного времени горничной уходит на уборку номеров,
--       остальное — переходы, бельё, перерывы (сверено с [N1]: 12–16 номеров
--       за смену при 20–35 мин на номер).
--  [D3] Допущение: доля гостей, отказавшихся от ежедневной уборки, если
--       предложить это за бонус («зелёная опция»). Данных по России нет.
CREATE OR REPLACE TEMP TABLE assumptions AS
SELECT * FROM (VALUES
--  сценарий     номеров ночей вых.мин тек.мин прод.доля зп_горн зп_админ взносы часов/мес экономия_мин отказ_от_уборки стойка_мин киоск_мин доля_киоска
    ('осторожный', 150,   3.0,  25,     15,     0.80,     55000,  60000,   0.30,  164,      1,           0.10,           8,         1,        0.30),
    ('базовый',    150,   2.5,  35,     20,     0.80,     70000,  75000,   0.30,  164,      1,           0.25,          10,         1,        0.40),
    ('смелый',     150,   2.0,  45,     25,     0.80,     85000,  90000,   0.30,  164,      1,           0.40,          15,         1,        0.50)
) t(scenario, rooms, los, min_checkout, min_stayover, productive_share,
    maid_wage, admin_wage, payroll_tax, hours_per_month,
    min_saved, optout_share, desk_min, kiosk_staff_min, kiosk_share);
-- desk_min / kiosk_staff_min — время СОТРУДНИКА на одно заселение: на стойке
-- и когда гость заселяется сам (сотрудник иногда помогает — 1 мин).

-- 1. Месячная модель ---------------------------------------------------------------
CREATE OR REPLACE TEMP VIEW pm_month AS
SELECT
    a.scenario,
    m.month,
    m.occupancy_label / 100.0                              AS occ,
    m.adr_est                                              AS adr,
    DAY(LAST_DAY(MAKE_DATE(2025, m.month, 1)))             AS days,
    a.rooms * DAY(LAST_DAY(MAKE_DATE(2025, m.month, 1))) * m.occupancy_label / 100.0 AS sold_rn,
    a.*
FROM monthly_chart m
CROSS JOIN assumptions a
WHERE m.year = 2025;

CREATE OR REPLACE TEMP VIEW pm_calc AS
SELECT
    scenario, month, occ, adr, sold_rn,
    sold_rn * adr                                            AS room_revenue,
    sold_rn / los                                            AS departures,   -- = заездам
    sold_rn - sold_rn / los                                  AS stayovers,
    -- оплаченные часы горничных
    (sold_rn / los * min_checkout + (sold_rn - sold_rn / los) * min_stayover)
        / 60 / productive_share                              AS maid_hours,
    maid_wage * (1 + payroll_tax) / hours_per_month          AS maid_hour_cost,
    admin_wage * (1 + payroll_tax) / hours_per_month         AS admin_hour_cost,
    hours_per_month, maid_wage, payroll_tax, productive_share,
    min_saved, optout_share, min_stayover, desk_min, kiosk_staff_min, kiosk_share, los
FROM pm_month;

-- 2. Сколько стоит уборка номеров --------------------------------------------------
SELECT
    scenario,
    ROUND(SUM(maid_hours) / 12 / MAX(hours_per_month), 1)          AS maids_fte_avg,
    ROUND(SUM(maid_hours * maid_hour_cost) / 1e6, 1)               AS cleaning_cost_mln,
    ROUND(SUM(maid_hours * maid_hour_cost) / SUM(sold_rn))         AS cost_per_sold_room,
    ROUND(SUM(maid_hours * maid_hour_cost) / SUM(room_revenue) * 100, 1) AS pct_of_room_revenue
FROM pm_calc
GROUP BY scenario
ORDER BY cleaning_cost_mln;

-- 3. Четыре рычага: экономия в год и в «эквиваленте повышения цены» -----------------
-- «Эквивалент цены» = экономия / выручка номерного фонда. Столько процентов
-- пришлось бы добавить к цене номера (без потери гостей), чтобы заработать
-- столько же.
WITH lev AS (
    SELECT
        scenario,
        SUM(room_revenue) AS revenue,
        -- А. Минус одна минута на каждой уборке
        SUM((departures + stayovers) * min_saved / 60 / productive_share * maid_hour_cost) AS a_minute,
        -- Б. Часть гостей отказывается от ежедневной уборки
        SUM(stayovers * optout_share * min_stayover / 60 / productive_share * maid_hour_cost) AS b_optout,
        -- В. Штат под месяц, а не под пик: сколько стоят «лишние» часы, если
        --    держать постоянный штат под самый загруженный месяц (верхняя граница)
        MAX(maid_hours / hours_per_month) * 12 * MAX(maid_wage) * (1 + MAX(payroll_tax))
            - SUM(maid_hours * maid_hour_cost)                                      AS c_peak_staff,
        -- Г. Киоск самозаселения: время администраторов
        SUM(departures * kiosk_share * (desk_min - kiosk_staff_min) / 60 * admin_hour_cost) AS d_kiosk,
        SUM(departures * kiosk_share * (desk_min - kiosk_staff_min) / 60) / 12 / MAX(hours_per_month) AS d_kiosk_fte
    FROM pm_calc
    GROUP BY scenario
)
SELECT
    scenario,
    ROUND(a_minute / 1e6, 2)            AS a_minute_mln,
    ROUND(a_minute / revenue * 100, 2)  AS a_price_eq_pct,
    ROUND(b_optout / 1e6, 2)            AS b_optout_mln,
    ROUND(b_optout / revenue * 100, 2)  AS b_price_eq_pct,
    ROUND(c_peak_staff / 1e6, 2)        AS c_peak_staff_mln,
    ROUND(c_peak_staff / revenue * 100, 2) AS c_price_eq_pct,
    ROUND(d_kiosk / 1e6, 2)             AS d_kiosk_mln,
    ROUND(d_kiosk / revenue * 100, 2)   AS d_price_eq_pct,
    ROUND(d_kiosk_fte, 2)               AS d_kiosk_fte
FROM lev
ORDER BY a_minute_mln;

-- 4. Сезонность нагрузки: сколько горничных нужно в каждом месяце (базовый сценарий)
SELECT
    month,
    ROUND(occ * 100)                          AS occ_pct,
    ROUND(maid_hours / hours_per_month, 1)    AS maids_fte_needed
FROM pm_calc
WHERE scenario = 'базовый'
ORDER BY month;
