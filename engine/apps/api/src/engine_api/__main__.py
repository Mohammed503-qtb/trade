"""نقطة دخول uvicorn: `python -m engine_api`."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "engine_api.main:app",
        host=os.getenv("ENGINE_API_HOST", "127.0.0.1"),
        port=int(os.getenv("ENGINE_API_PORT", "4001")),
        log_level="info",
    )


if __name__ == "__main__":
    main()
