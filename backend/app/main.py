from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.services.mqtt_consumer import connect_mqtt
import psycopg

connection_uri = "postgresql://vanguard:vanguard@localhost:5432/telemetry"

@asynccontextmanager
async def lifespan(app: FastAPI):

    conn = psycopg.connect(connection_uri, autocommit=True)
    client = connect_mqtt(conn)
    client.loop_start()
    yield
    client.disconnect()
    client.loop_stop()
    conn.close()

app = FastAPI(title="Vanguard OT", lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok"}