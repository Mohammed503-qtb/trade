"""الإعدادات المركزية — تُقرأ من engine/.env أو متغيرات البيئة (§37.1: لا أسرار في الشيفرة)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# المسار إلى جذر engine/ — الحزمة على عمق ثابت:
# engine/packages/common/src/common/config.py → parents[4] = engine
# (يتطابق أيضًا مع التخطيط داخل حاوية الهدف: /app/packages/… → /app)
_ENGINE_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    """كل إعدادات المحرك — مصدر وحيد، لا قيم سحرية مبعثرة."""

    model_config = SettingsConfigDict(
        env_file=str(_ENGINE_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # وضع التشغيل: dev (sandbox) | target (خادم الهدف)
    engine_env: str = Field(default="dev", alias="ENGINE_ENV")

    # PostgreSQL — مسبوق بـ ENGINE_ لتفادي التصادم مع DATABASE_URL العام (Prisma في sandbox)
    database_url: str = Field(
        default="postgresql://engine:engine@127.0.0.1:5543/engine",
        alias="ENGINE_DATABASE_URL",
    )
    postgres_port: int = Field(default=5543, alias="POSTGRES_PORT")
    postgres_user: str = Field(default="engine", alias="POSTGRES_USER")
    postgres_password: str = Field(default="engine", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="engine", alias="POSTGRES_DB")

    # NATS
    nats_url: str = Field(default="nats://127.0.0.1:4222", alias="NATS_URL")
    nats_monitor_port: int = Field(default=8222, alias="NATS_MONITOR_PORT")

    # MinIO
    s3_endpoint: str = Field(default="127.0.0.1:9100", alias="S3_ENDPOINT")
    s3_access_key: str = Field(default="engine", alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="", alias="S3_SECRET_KEY")
    s3_bucket: str = Field(default="engine-raw", alias="S3_BUCKET")
    s3_secure: bool = Field(default=False, alias="S3_SECURE")

    # engine-api
    engine_api_host: str = Field(default="127.0.0.1", alias="ENGINE_API_HOST")
    engine_api_port: int = Field(default=4001, alias="ENGINE_API_PORT")

    # TradingView webhook (المرحلة 10)
    tv_webhook_secret: str = Field(default="", alias="TV_WEBHOOK_SECRET")

    # Binance (D-02)
    binance_api_base: str = Field(default="https://fapi.binance.com", alias="BINANCE_API_BASE")
    binance_vision_base: str = Field(
        default="https://data.binance.vision", alias="BINANCE_VISION_BASE"
    )
    engine_symbol: str = Field(default="BTCUSDT", alias="ENGINE_SYMBOL")

    # الأطر الزمنية (D-05)
    engine_timeframe_htf: str = Field(default="1h", alias="ENGINE_TIMEFRAME_HTF")
    engine_timeframe_mtf: str = Field(default="15m", alias="ENGINE_TIMEFRAME_MTF")
    engine_timeframe_ltf: str = Field(default="1m", alias="ENGINE_TIMEFRAME_LTF")


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """إعدادات مُخزَّنة مؤقتًا — كائن مجمّد واحد لكل العملية."""
    return Settings()
