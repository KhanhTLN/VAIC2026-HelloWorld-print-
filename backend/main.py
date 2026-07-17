from fastapi import FastAPI

from core.config import settings

app = FastAPI(title=settings.app_name)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
