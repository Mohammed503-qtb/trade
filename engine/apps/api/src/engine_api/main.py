"""engine-api — FastAPI: webhook، حالة، سيناريوهات (§5.5 + build_plan §B).

المرحلة 0: هيكل إقلاع + فحص صحة. المرحلة 10: الويبهوك (§36/D-09) و
مسارات اللوحة (§35) فوق تركيب البوابات الحتمي — الوعود مسددة.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import schemas
import structlog
from common.config import load_settings
from fastapi import FastAPI

from .api import dashboard, webhook
from .settings_bridge import close_pool, init_pool

log = structlog.get_logger(__name__)

VERSION = schemas.__version__


async def _warm_composition() -> None:
    """تسخير تركيب اللوحة مرة واحدة عند الإقلاع — بخيط منفصل كي لا
    تسدّ الحلقة (بناء السلسلة الحتمية عمل حسابي ثقيل بلا عمليات إدخال)."""
    import asyncio

    from .composition import build_overview

    try:
        await asyncio.to_thread(build_overview)
        log.info("composition_warm")
    except Exception as exc:  # pragma: no cover — تحوط تشغيلي موثق
        log.error("composition_warm_failed", error=repr(exc))


@asynccontextmanager
async def _lifespan(app: FastAPI) -> Any:
    """دورة الحياة: مجموعة الاتصال ثم تسخير التوليف قبل الخدمة."""
    import asyncio

    await init_pool()
    warm = asyncio.create_task(_warm_composition())
    log.info("engine_api_startup")
    yield
    warm.cancel()
    await close_pool()
    log.info("engine_api_shutdown")


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(
        title="AI Market Reasoning Engine API",
        version=VERSION,
        docs_url="/docs",
        lifespan=_lifespan,
    )
    app.include_router(webhook.router)
    app.include_router(dashboard.router)

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        """فحص الصحة — يستهلكه supervisor والبوابة."""
        return {
            "status": "ok",
            "service": "engine-api",
            "version": VERSION,
            "engine_env": settings.engine_env,
            "schema_version": schemas.SCHEMA_VERSION,
        }

    @app.get("/readyz")
    async def readyz() -> dict[str, Any]:
        """الجهوزية — تفصل الإقلاع عن الاعتماد على البنية التحتية."""
        return {"status": "ready"}

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    settings = load_settings()
    uvicorn.run(
        "engine_api.main:app",
        host=os.getenv("ENGINE_API_HOST", "127.0.0.1"),
        port=int(os.getenv("ENGINE_API_PORT", "4001")),
        log_level="info",
    )
