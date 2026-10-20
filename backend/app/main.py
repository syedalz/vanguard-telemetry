from fastapi import FastAPI

app = FastAPI(title="Vanguard OT")


@app.get("/health")
def health():
    return {"status": "ok"}