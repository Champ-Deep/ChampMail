from fastapi import FastAPI

from app.api.v1 import router as v1_router
from app.config import get_settings

get_settings()  # raises at import, so uvicorn exits, when production secrets are unset

app = FastAPI(title="ChampMail v3")
app.include_router(v1_router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
