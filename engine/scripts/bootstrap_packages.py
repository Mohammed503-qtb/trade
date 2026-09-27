#!/usr/bin/env python3
"""يولّد pyproject.toml + بنية src لكل حزم workspace (تشغيل مرة واحدة عند التأسيس)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (مسار, اسم التوزيع, اسم الاستيراد, وصف, تبعيات مشروع, تبعيات خارجية)
PKGS = [
    # ══ packages (الأساس) ══
    (
        "packages/schemas",
        "engine-schemas",
        "schemas",
        "نماذج Pydantic v2 — مصدر الحقيقة الوحيد لكل الرسائل وحقول JSONB (§32)",
        [],
        ["pydantic>=2.9"],
    ),
    (
        "packages/common",
        "engine-common",
        "common",
        "وقت-حدث، معرفات، سجلات منظمة، hot-state (§47 packages/common)",
        [],
        ["pydantic>=2.9", "pydantic-settings>=2.6", "structlog>=24.4", "prometheus-client>=0.21"],
    ),
    (
        "packages/math",
        "engine-math",
        "quantmath",
        "رياضيات نقية: ATR، مئينيات، z-scores، تشبع — لا تستورد أي حزمة مشروع",
        [],
        ["numpy>=2.1"],
    ),
    (
        "packages/features",
        "engine-features",
        "features",
        "السمات الحسابية — مسار واحد للحي والإعادة (A-02)",
        ["engine-schemas", "engine-common", "engine-math"],
        [],
    ),
    (
        "packages/backtest",
        "engine-backtest",
        "backtest",
        "محرك الإعادة، التكاليف، الوسم، المقاييس (§25-§26, §30)",
        ["engine-schemas", "engine-common", "engine-math", "engine-features"],
        [],
    ),
    # ══ services ══
    (
        "services/ingestion",
        "engine-ingestion",
        "ingestion",
        "محول Binance، تنقيح، جودة، بناء شموع (§7, §8)",
        ["engine-schemas", "engine-common"],
        [],
    ),
    (
        "services/market_state",
        "engine-market-state",
        "market_state",
        "السياق: نظام، جلسات، HTF/MTF، تقلب (§9, §16)",
        ["engine-schemas", "engine-common", "engine-features"],
        [],
    ),
    (
        "services/liquidity",
        "engine-liquidity",
        "liquidity",
        "خريطة السيولة، sweep، أهداف (§10)",
        ["engine-schemas", "engine-common", "engine-features"],
        [],
    ),
    (
        "services/structure",
        "engine-structure",
        "structure",
        "swings، BOS/CHoCH، displacement، FVG، OB، premium/discount (§11)",
        ["engine-schemas", "engine-common", "engine-features"],
        [],
    ),
    (
        "services/orderflow",
        "engine-orderflow",
        "orderflow",
        "delta/POC/VA، امتصاص، إنهاك، اختلالات (§12)",
        ["engine-schemas", "engine-common", "engine-features"],
        [],
    ),
    (
        "services/patterns",
        "engine-patterns",
        "patterns",
        "شموع + كلاسيكي (§13) — الهارمونيك (§14) مؤجل صراحة بعد MVP",
        ["engine-schemas", "engine-common", "engine-features"],
        [],
    ),
    (
        "services/fusion",
        "engine-fusion",
        "fusion",
        "دمج الدليل، ارتباط، تناقض (§19)",
        ["engine-schemas", "engine-common", "engine-features"],
        [],
    ),
    (
        "services/scenarios",
        "engine-scenarios",
        "scenarios",
        "مقترحات + دورة حياة + مشغلات (§18)",
        ["engine-schemas", "engine-common", "engine-features"],
        [],
    ),
    (
        "services/risk",
        "engine-risk",
        "risk",
        "لا-تداول (§22)، R، تحجيم، قيود (§23)",
        ["engine-schemas", "engine-common", "engine-features"],
        [],
    ),
    (
        "services/learning",
        "engine-learning",
        "learning",
        "دفتر التجارب (كتابة §29.1) — التحليلات مؤجلة بعد MVP",
        ["engine-schemas", "engine-common"],
        [],
    ),
    # ══ apps ══
    (
        "apps/api",
        "engine-api",
        "engine_api",
        "FastAPI: webhook، حالة، سيناريوهات (§5.5)",
        ["engine-schemas", "engine-common"],
        ["fastapi>=0.115", "uvicorn[standard]>=0.32"],
    ),
    (
        "apps/worker",
        "engine-worker",
        "engine_worker",
        "عملية خط الأنابيب الحية: ingestion→…→risk (build_plan A.1)",
        ["engine-schemas", "engine-common"],
        ["nats-py>=2.8", "asyncpg>=0.30", "minio>=7.2", "structlog>=24.4", "httpx>=0.28"],
    ),
    (
        "apps/replay",
        "engine-replay",
        "engine_replay",
        "مشغل الإعادة/الاختبارات CLI (§26)",
        ["engine-schemas", "engine-common", "engine-backtest"],
        ["typer>=0.12"],
    ),
]


def pyproject(dist: str, imp: str, desc: str, proj_deps: list[str], ext_deps: list[str]) -> str:
    deps = ", ".join(f'"{d}"' for d in (ext_deps + proj_deps))
    return f'''[project]
name = "{dist}"
version = "0.1.0"
description = "{desc}"
requires-python = ">=3.12"
dependencies = [{deps}]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{imp}"]
'''


for path, dist, imp, desc, proj_deps, ext_deps in PKGS:
    pkg_dir = ROOT / path
    src_dir = pkg_dir / "src" / imp
    src_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "pyproject.toml").write_text(
        pyproject(dist, imp, desc, proj_deps, ext_deps), encoding="utf-8"
    )
    init = src_dir / "__init__.py"
    if not init.exists():
        init.write_text(
            f'"""{desc}"""\n\n__version__ = "0.1.0"\n',
            encoding="utf-8",
        )
    print(f"OK {dist:22s} -> {path}/src/{imp}")

print("\nتم توليد", len(PKGS), "حزمة")
