-- One row per sensor reading published by an asset
CREATE TABLE telemetry_messages (
    asset_id TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    seq BIGINT NOT NULL,
    engine_temp_c DOUBLE PRECISION NOT NULL,
    hyd_pressure_bar DOUBLE PRECISION NOT NULL,
    vibration_mm_s DOUBLE PRECISION NOT NULL,
    fuel_pct DOUBLE PRECISION NOT NULL,
    -- Also lets the backend skip duplicate messages with ON CONFLICT
    PRIMARY KEY (asset_id, timestamp)
);

-- Turn the table into a TimescaleDB hypertable partitioned by time
SELECT create_hypertable('telemetry_messages', 'timestamp');

-- One row per alert; resolved_at is NULL while the alert is still open
CREATE TABLE alerts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_id TEXT NOT NULL,
    sensor TEXT NOT NULL,
    opened_value DOUBLE PRECISION NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    methods TEXT[] NOT NULL
);

-- At most one open alert per asset and sensor
CREATE UNIQUE INDEX alerts_one_open_per_sensor
    ON alerts (asset_id, sensor)
    WHERE resolved_at IS NULL;

