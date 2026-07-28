-- dimension ville
CREATE TABLE IF NOT EXISTS dim_city (
    city_id SERIAL PRIMARY KEY,
    city_name TEXT NOT NULL UNIQUE,
    country TEXT DEFAULT 'FR'
);

-- dimension paramètre (polluant)
CREATE TABLE IF NOT EXISTS dim_parameter (
    parameter_id SERIAL PRIMARY KEY,
    parameter_name TEXT NOT NULL UNIQUE,
    unit TEXT
);

-- dimension date et heure
CREATE TABLE IF NOT EXISTS dim_date (
    date_id SERIAL PRIMARY KEY,
    full_timestamp TIMESTAMPTZ NOT NULL UNIQUE,
    date DATE NOT NULL,
    year INT NOT NULL,
    month INT NOT NULL,
    day INT NOT NULL,
    hour INT NOT NULL,
    day_of_week INT NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_air_quality (
    id BIGSERIAL PRIMARY KEY,
    city_id INT NOT NULL REFERENCES dim_city(city_id),
    parameter_id INT NOT NULL REFERENCES dim_parameter(parameter_id),
    date_id INT NOT NULL REFERENCES dim_date(date_id),
    value NUMERIC,
    inserted_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (city_id, parameter_id, date_id)
);

CREATE INDEX IF NOT EXISTS idx_fact_city ON fact_air_quality(city_id);
CREATE INDEX IF NOT EXISTS idx_fact_parameter ON fact_air_quality(parameter_id);
CREATE INDEX IF NOT EXISTS idx_fact_date ON fact_air_quality(date_id);
