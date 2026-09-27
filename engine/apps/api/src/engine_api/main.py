"""engine-api — FastAPI: webhook، حالة، سيناريوهات (§5.5).

المرحلة 0: هيكل إقلاع + فحص صحة فقط. المسارات الوظيفية تُبنى في مراحلها.
"""

from __future__ import annotations

import os
from typing import Any

import schemas
import structlog
from common.config import load_settings
from fastapi import FastAPI

log = structlog.get_logger(__name__)

VERSION = schemas.__version__


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(
        title="AI Market Reasoning Engine API",
        version=VERSION,
        docs_url="/docs",
    )

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
        """الجهوزية — تفصل الإقلاع عن الاعتماد على البنية التحتية (تُوسّع لاحقًا)."""
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
