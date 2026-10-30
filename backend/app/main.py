from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.services.mqtt_consumer import connect_mqtt, handle_events
from app.services.anomaly import ZScoreDetector, AlertManager
import psycopg
from datetime import datetime, timezone
import asyncio

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
    task = asyncio.create_task(watch_for_stale_trucks(conn,manager))
    yield
    # Shutdown: stop the stale-truck timer and consuming before closing the database connection
    task.cancel()
    # cancel() only requests it, so wait for the task to actually finish
    try:
        await task
    except asyncio.CancelledError:
        pass
    client.disconnect()
    client.loop_stop()
    conn.close()


async def watch_for_stale_trucks(conn, manager):

    cur = conn.cursor()

   
    while True:
        try:
            events = manager.check_stale(datetime.now(timezone.utc))
            handle_events(cur, events)
            
        except psycopg.Error as e:
            print(f"Stale check failed: {e}")

        await asyncio.sleep(2)
        
   
app = FastAPI(title="Vanguard OT", lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok"}