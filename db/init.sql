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
