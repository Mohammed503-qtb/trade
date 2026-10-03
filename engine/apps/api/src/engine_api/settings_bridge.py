"""جسر الحالة التشغيلية للواجهة — إعدادات ومجموعة اتصال مشتركة.

نمط ADR-007: الواجهة عملية مستقلة عن supervisor؛ مجموعتها تُنشأ في
lifespan وتغلق مع الإطفاء — لا اتصال لكل طلب (عقد asyncpg الرسمي).
"""

from __future__ import annotations

from typing import Any

import asyncpg
from common.config import Settings, load_settings

_pool: asyncpg.Pool | None = None
_settings: Settings | None = None
_state: dict[str, Any] = {}


async def init_pool() -> asyncpg.Pool:
    """إنشاء المجموعة مرة واحدة لكل عملية (تستدعى من lifespan)."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(get_settings().database_url, min_size=1, max_size=4)
    return _pool


async def close_pool() -> None:
    """إغلاق المجموعة عند الإطفاء الرشيق."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """المجموعة الجاهزة — لا تستدعى قبل startup."""
    if _pool is None:
        raise RuntimeError("connection pool not initialized — app startup incomplete")
    return _pool


def get_settings() -> Settings:
    """الإعدادات المحمّلة (تجميد مفرد لكل عملية)."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings
