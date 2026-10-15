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
from .routers import datasources, settings, simulator, tasks
from .seed import seed_if_empty
from .services import data_adapter as da
from .services import scheduler_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # 轻量迁移：旧库补 conflict_resolution 列
    from sqlalchemy import text

    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE monitor_tasks ADD COLUMN conflict_resolution JSON"))
        except Exception:  # noqa: BLE001
            pass  # 列已存在
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
app.include_router(settings.router, prefix="/api/v1", tags=["settings"])


@app.get("/architecture", include_in_schema=False)
async def architecture_diagram():
    return FileResponse(Path(__file__).resolve().parents[2] / "docs" / "live-panel" / "index.html")


@app.get("/architecture/technical", include_in_schema=False)
async def technical_architecture_diagram():
    return FileResponse(Path(__file__).resolve().parents[2] / "docs" / "live-panel" / "technical.html")


@app.get("/demo/alpharadar-demo-180s.mp4", include_in_schema=False)
async def product_demo_video():
    return FileResponse(
        Path(__file__).resolve().parents[2] / "docs" / "demo" / "alpharadar-demo-180s.mp4",
        media_type="video/mp4",
    )


# ---- 生产环境：托管前端静态产物（单进程，无跨域）----
# 优先使用本地构建目录 frontend_dist（存在则说明是 Docker/本地 npm run build 产物），
# 否则回退到仓库内已提交的预构建产物 frontend/dist，保证「pip install + uvicorn」即可完整运行
_candidates = [
    Path(__file__).resolve().parent.parent.parent / "frontend_dist",
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist",
]
frontend_dist = next((p for p in _candidates if p.exists() and (p / "index.html").exists()), None)
if frontend_dist:
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return {"error": "API endpoint not found"}
        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"error": "frontend not built"}
