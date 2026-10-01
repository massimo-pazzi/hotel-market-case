-- Подключение данных кейса к DuckDB.
-- Запуск из корня проекта:  duckdb   затем   .read sql/setup.sql
--
-- VIEW (представление) — это сохранённый запрос с именем. Сами данные остаются
-- в CSV, поэтому если скрипт в scripts/ перезапишет файл, представление сразу
-- покажет новые данные.

CREATE OR REPLACE VIEW indicators AS
SELECT * FROM read_csv('data/clean/nf_key_indicators.csv');

CREATE OR REPLACE VIEW openings AS
SELECT * FROM read_csv('data/clean/nf_openings.csv');

-- Ряды 2016–2025 с графиков S1 (ADR, RevPAR, фонд — оценки по столбцам, см. SOURCES.md)
CREATE OR REPLACE VIEW annual_chart AS
SELECT * FROM read_csv('data/clean/nf_annual_chart.csv');

CREATE OR REPLACE VIEW monthly_chart AS
SELECT * FROM read_csv('data/clean/nf_monthly_chart.csv');

CREATE OR REPLACE VIEW tourist_flow AS
SELECT * FROM read_csv('data/clean/tourist_flow_chart.csv');

CREATE OR REPLACE VIEW supply_chart AS
SELECT * FROM read_csv('data/clean/nf_supply_chart.csv');

-- IBC Real Estate по данным Hotel Advisors (другая выборка: классические отели 3–5* от 100 номеров)
CREATE OR REPLACE VIEW ibc_segments AS
SELECT * FROM read_csv('data/clean/ibc_h1_segments.csv');   -- Петербург и Москва

CREATE OR REPLACE VIEW ibc_city_revpar AS
SELECT * FROM read_csv('data/clean/ibc_city_revpar_h1_2026.csv');

CREATE OR REPLACE VIEW ibc_placed AS
SELECT * FROM read_csv('data/clean/ibc_placed_persons_2026.csv');

CREATE OR REPLACE VIEW ibc_annual AS
SELECT * FROM read_csv('data/clean/ibc_spb_annual.csv');

-- Росстат: зарплаты (Россия по отраслям, Петербург по экономике) и ИПЦ декабрь к декабрю
CREATE OR REPLACE VIEW rosstat AS
SELECT * FROM read_csv('data/clean/rosstat_wages_cpi.csv');

-- Росстат: номера и размещённые лица по регионам, 2015–2025 (S21)
CREATE OR REPLACE VIEW regions AS
SELECT * FROM read_csv('data/clean/rosstat_regions_rooms_guests.csv');
