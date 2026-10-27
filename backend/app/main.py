from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.services.mqtt_consumer import connect_mqtt
from app.services.anomaly import ZScoreDetector, AlertManager
import psycopg

connection_uri = "postgresql://vanguard:vanguard@localhost:5432/telemetry"

# Runs the MQTT consumer for as long as the API is up
@asynccontextmanager
async def lifespan(app: FastAPI):

    # autocommit so each inserted reading is saved immediately
    conn = psycopg.connect(connection_uri, autocommit=True)
    detector = ZScoreDetector()
    manager = AlertManager()
    # Alerts left open by the last run can't be tracked anymore (the AlertManager
    # starts empty), so close them before new alerts can open for the same sensors
    resolve_query = """

        UPDATE alerts
        SET resolved_at = NOW()
        WHERE resolved_at IS NULL


    """
    cur = conn.cursor()
    cur.execute(resolve_query)
    count = cur.rowcount

    print(f"Closed {count} alerts left open by the last run.")
    client = connect_mqtt(conn, detector, manager)
    # Handles MQTT traffic on a background thread
    client.loop_start()
    yield
    # Shutdown: stop consuming before closing the database connection
    client.disconnect()
    client.loop_stop()
    conn.close()

app = FastAPI(title="Vanguard OT", lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok"}