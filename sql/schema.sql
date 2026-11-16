-- =====================================================================
-- Data Warehouse Kayak – schéma PostgreSQL (AWS RDS)
-- Chargé par notebooks/05_etl_s3_to_rds.ipynb (rechargement complet à chaque exécution)
-- =====================================================================

-- Suppression dans l'ordre inverse des dépendances (vue, puis tables liées, puis tables de référence)
DROP VIEW IF EXISTS v_kayak_enriched;
DROP TABLE IF EXISTS destination_hotels;
DROP TABLE IF EXISTS hotels;
DROP TABLE IF EXISTS destinations;

-- ---------------------------------------------------------------------
-- Destinations : une ligne par ville, avec ses indicateurs météo à 7 jours
-- ---------------------------------------------------------------------
CREATE TABLE destinations (
    city_id              SMALLINT         PRIMARY KEY,
    city_name            VARCHAR(100)     NOT NULL UNIQUE,
    latitude             DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude            DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    weather_period_start DATE             NOT NULL,
    weather_period_end   DATE             NOT NULL,
    total_rain_mm        NUMERIC(6, 1)    NOT NULL CHECK (total_rain_mm >= 0),
    avg_pop              NUMERIC(3, 2)    NOT NULL CHECK (avg_pop BETWEEN 0 AND 1),
    avg_temp_day         NUMERIC(4, 1)    NOT NULL,
    rainy_days           SMALLINT         NOT NULL CHECK (rainy_days BETWEEN 0 AND 7),
    weather_score        NUMERIC(4, 3)    NOT NULL CHECK (weather_score BETWEEN 0 AND 1),
    weather_rank         SMALLINT         NOT NULL CHECK (weather_rank >= 1),
    CHECK (weather_period_end >= weather_period_start)
);

-- ---------------------------------------------------------------------
-- Hôtels : une ligne par établissement (dédoublonné sur l'identifiant Booking)
-- ---------------------------------------------------------------------
CREATE TABLE hotels (
    hotel_id              BIGINT           PRIMARY KEY,           -- identifiant Booking
    hotel_name            VARCHAR(255)     NOT NULL,
    hotel_url             TEXT             NOT NULL,
    accommodation_type_id SMALLINT         NOT NULL,              -- 204 = hôtel (nomenclature Booking)
    latitude              DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude             DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    address               TEXT,
    hotel_city            VARCHAR(100),
    review_score          NUMERIC(3, 1)    CHECK (review_score BETWEEN 0 AND 10),  -- vide = pas encore noté
    review_count          INTEGER          NOT NULL CHECK (review_count >= 0),
    star_rating           SMALLINT         CHECK (star_rating BETWEEN 1 AND 5),    -- vide = non classé
    description           TEXT,
    collected_at          TIMESTAMPTZ      NOT NULL
);

-- ---------------------------------------------------------------------
-- Table d'association : un hôtel peut être proposé pour plusieurs destinations voisines
-- (ex. : un hôtel de Colmar proposé aussi pour Eguisheim)
-- ---------------------------------------------------------------------
CREATE TABLE destination_hotels (
    city_id         SMALLINT      NOT NULL REFERENCES destinations (city_id) ON DELETE CASCADE,
    hotel_id        BIGINT        NOT NULL REFERENCES hotels (hotel_id) ON DELETE CASCADE,
    search_position SMALLINT      NOT NULL CHECK (search_position >= 1),  -- rang dans les résultats Booking
    distance_km     NUMERIC(5, 1) NOT NULL CHECK (distance_km >= 0),      -- distance hôtel <-> destination
    PRIMARY KEY (city_id, hotel_id)
);
CREATE INDEX idx_destination_hotels_hotel_id ON destination_hotels (hotel_id);

-- ---------------------------------------------------------------------
-- Vue "à plat" : restitue exactement les données du fichier enrichi stocké dans S3
-- (processed/kayak_enriched.csv) – exigence de l'énoncé
-- ---------------------------------------------------------------------
CREATE VIEW v_kayak_enriched AS
SELECT
    d.city_id,
    d.city_name,
    d.latitude  AS city_latitude,
    d.longitude AS city_longitude,
    d.weather_period_start,
    d.weather_period_end,
    d.total_rain_mm,
    d.avg_pop,
    d.avg_temp_day,
    d.rainy_days,
    d.weather_score,
    d.weather_rank,
    h.hotel_id,
    h.hotel_name,
    h.hotel_url,
    dh.search_position,
    h.latitude  AS hotel_latitude,
    h.longitude AS hotel_longitude,
    h.address,
    h.hotel_city,
    dh.distance_km,
    h.review_score,
    h.review_count,
    h.star_rating,
    h.description,
    h.collected_at AS hotels_collected_at
FROM destination_hotels AS dh
JOIN destinations AS d ON d.city_id = dh.city_id
JOIN hotels       AS h ON h.hotel_id = dh.hotel_id;
