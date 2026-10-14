"""AlphaRadar · 可配置投资监控与风险雷达 —— FastAPI 入口。"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .database import Base, SessionLocal, engine
from .routers import datasources, simulator, tasks
from .seed import seed_if_empty
from .services import data_adapter as da
from .services import scheduler_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()
    await da.refresh_calendar()
    if os.getenv("DISABLE_SCHEDULER", "").lower() not in ("1", "true"):
        scheduler_engine.start_scheduler()
    yield
    scheduler_engine.stop_scheduler()


app = FastAPI(title="AlphaRadar 可配置投资监控与风险雷达 API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])
app.include_router(datasources.router, prefix="/api/v1/datasources", tags=["datasources"])
app.include_router(simulator.router, prefix="/api/v1/simulator", tags=["simulator"])


# ---- 生产环境：挂载前端编译产物（单容器部署，无跨域）----
frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend_dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return {"error": "API endpoint not found"}
        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"error": "frontend not built"}
