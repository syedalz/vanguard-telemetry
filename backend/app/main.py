from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.services.mqtt_consumer import connect_mqtt

@asynccontextmanager
async def lifespan(app: FastAPI):
    client = connect_mqtt()
    client.loop_start()
    yield
    client.disconnect()
    client.loop_stop()

app = FastAPI(title="Vanguard OT", lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok"}