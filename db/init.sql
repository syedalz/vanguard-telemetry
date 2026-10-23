CREATE TABLE telemetry_messages (
    asset_id TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    seq BIGINT NOT NULL,
    engine_temp_c DOUBLE PRECISION NOT NULL,
    hyd_pressure_bar DOUBLE PRECISION NOT NULL,
    vibration_mm_s DOUBLE PRECISION NOT NULL,
    fuel_pct DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (asset_id, timestamp)
);

SELECT create_hypertable('telemetry_messages', 'timestamp');
