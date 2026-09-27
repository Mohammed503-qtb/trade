"""اختبارات وحدة التأسيس — تثبت أن الـworkspace سليم قبل أي بناء فوقه."""

from __future__ import annotations

import importlib

import pytest

# كل حزم المشروع الثمانية عشر — إثبات أن البيئة قابلة للإقلاع كاملة
ALL_PACKAGES = [
    "schemas",
    "common",
    "quantmath",
    "features",
    "backtest",
    "ingestion",
    "market_state",
    "liquidity",
    "structure",
    "orderflow",
    "patterns",
    "fusion",
    "scenarios",
    "risk",
    "learning",
    "engine_api",
    "engine_worker",
    "engine_replay",
]


@pytest.mark.parametrize(("package",), [(p,) for p in ALL_PACKAGES])
def test_package_imports_cleanly(package: str) -> None:
    """كل حزمة تستورد بلا أخطاء — الأساس الذي تقف عليه كل المراحل."""
    mod = importlib.import_module(package)
    assert hasattr(mod, "__version__")


def test_schema_version_pinned() -> None:
    """إصدار المخططات قانوني (semantic) — عقود الرسائل مُدارة إصداريًا (§32)."""
    import schemas

    parts = schemas.SCHEMA_VERSION.split(".")
    assert len(parts) == 3, "يجب أن يكون semver كامل major.minor.patch"
    assert all(p.isdigit() for p in parts)


def test_settings_are_frozen_and_prefixed() -> None:
    """الإعدادات مجمّدة (لا تعديل عرضي) وENGINE_DATABASE_URL لا يتصادم مع بيئة المنصة."""
    from common.config import Settings

    s = Settings(_env_file=None)
    assert s.engine_env == "dev"
    assert s.database_url.startswith("postgresql://")
    assert s.engine_timeframe_htf == "1h"
    # D-05: فصل الأدوار ثابت — القيم الافتراضية للسياق/التموضع/الإطلاق
    assert (s.engine_timeframe_htf, s.engine_timeframe_mtf, s.engine_timeframe_ltf) == (
        "1h",
        "15m",
        "1m",
    )
