from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from core.config import settings
from core.database import Base, engine
from routers import (
    assist_router,
    brands_router,
    categories_router,
    chat_router,
    products_router,
    search_router,
)

import models  # noqa: F401


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description="MVP AI Shopping Assistant — Chat tư vấn 3 tiêu chí → Top 3",
    lifespan=lifespan,
)

app.include_router(brands_router, prefix="/api/v1")
app.include_router(categories_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(assist_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
