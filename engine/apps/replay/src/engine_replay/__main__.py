"""engine-replay — مشغل الإعادة/الاختبارات (§26).

المرحلة 9: المحرك الفعلي — خط أنابيب الإعادة الميكانيكية (نية
معتمدة + شموع ⇒ تعبئات ووسم ومقاييس وتقرير §26.2) وأوامر WFO (§39.3)
فوق مكتبة ``backtest``. التركيب الكامل فوق السيناريوهات والمخاطرة
يعمل في سلسلة بوابات المراحل (verify_phase7/8/9).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import schemas
import typer
from backtest import (
    DEFAULT_SAMPLE_WFO_PROTOCOL,
    WFOProtocolError,
    default_backtest_config,
    research_protocol,
    split_windows,
)
from common.config import load_settings
from schemas import (
    BacktestIdentity,
    Candle,
    EntrySpec,
    WFOProtocolConfig,
)

from .backtest import run_backtest

app = typer.Typer(help="مشغل الإعادة والاختبارات العكسية (§26)")

verify = typer.Typer(help="أوامر تحقق الحتمية")
app.add_typer(verify, name="verify")


@app.command()
def info() -> None:
    """معلومات البيئة والإصدارات."""
    s = load_settings()
    typer.echo(f"schema_version : {schemas.SCHEMA_VERSION}")
    typer.echo(f"engine_env     : {s.engine_env}")
    typer.echo(f"symbol         : {s.engine_symbol}")
    tf = f"{s.engine_timeframe_htf}/{s.engine_timeframe_mtf}/{s.engine_timeframe_ltf}"
    typer.echo(f"htf/mtf/ltf    : {tf}")


@verify.command("phase0")
def verify_phase0() -> None:
    """تحقق المرحلة 0: الإعدادات تُحمّل والإصدارات متسقة."""
    load_settings()
    typer.echo("phase0: settings OK")


# ───────────────────────── إعادة ميكانيكية (§26 + بوابة 9) ─────────────────────────


@app.command()
def backtest(
    candles_path: Path = typer.Option(..., "--candles", help="JSON: قائمة شموع إطار التنفيذ"),
    specs_path: Path = typer.Option(..., "--specs", help="JSON: قائمة مواصفات دخول EntrySpec"),
    out_path: Path = typer.Option(..., "--out", help="ملف تقرير الإعادة الناتج"),
    data_snapshot_id: str = typer.Option(..., "--data-snapshot", help="معرف لقطة البيانات §26.2"),
    code_version: str = typer.Option("workspace", "--code-version", help="إصدار الكود"),
    model_version: str = typer.Option("none-mvp", "--model-version", help="إصدار النموذج"),
    parameter_set_version: str = typer.Option(
        "risk-default-v1", "--parameter-set", help="إصدار مجموعة المعاملات"
    ),
    random_seed: int = typer.Option(0, "--seed", help="بذرة الاستنساخ §26.2"),
) -> None:
    """إعادة ميكانيكية كاملة: نوايا معتمدة فوق شموع ⇒ تقرير §26.2 موثق.

    REALISTIC نمط القبول حصرًا والترتيب داخل الشمعة متحفظ (§30) —
    التقرير حتمي بايت-بايت ما عدا created_at_utc (الاستثناء الموثق).
    """
    candles = [Candle.model_validate(c) for c in _read_json(candles_path)]
    specs = [EntrySpec.model_validate(s) for s in _read_json(specs_path)]
    if not specs:
        typer.echo("✗ لا مواصفات دخول في الملف — لا إعادة بلا نوايا", err=True)
        raise typer.Exit(1)
    instruments = sorted({s.symbol for s in specs})
    start = min(s.decision_time for s in specs)
    end = max(s.expiry for s in specs)
    config = default_backtest_config()
    identity = BacktestIdentity(
        backtest_id="sealed-by-builder",
        data_snapshot_id=data_snapshot_id,
        code_version=code_version,
        model_version=model_version,
        parameter_set_version=parameter_set_version,
        cost_model_version=f"backtest-{config.fingerprint()[:12]}",
        random_seed=random_seed,
        start_time=start,
        end_time=end,
        instrument_set=tuple(instruments),
    )
    report, trades = run_backtest(
        specs=specs,
        candles=candles,
        identity=identity,
        config=config,
    )
    _write_json(out_path, json.loads(report.model_dump_json()))
    typer.echo(
        f"✓ إعادة كاملة: {len(trades)} صفقة محاكاة — "
        f"المُوسومة {report.metrics.labeled_trades} وغير المنفذة "
        f"{report.metrics.not_executable} والمفتوحة {report.metrics.open_at_data_end} — "
        f"التوقع الصافي {report.metrics.net_expectancy_r:.4f}R — "
        f"التقرير: {out_path}"
    )


@app.command()
def wfo(
    candidates_path: Path = typer.Option(
        ..., "--candidates", help="JSON: قائمة لحظات المرشحين (ISO-8601) مرتبة زمنيًا"
    ),
    out_path: Path = typer.Option(..., "--out", help="ملف تقرير WFO الناتج"),
    protocol: str = typer.Option(
        "research", "--protocol", help="research (2000/500/500 §39.3) أو sample (بنية العينة)"
    ),
    embargo_s: float = typer.Option(
        14_400.0, "--embargo-s", help="الحجز الزمني بالثواني (≥ أقصى أفق تقييم)"
    ),
) -> None:
    """تقسيم تدحرج أمامي (§39.3) — طيات مرتبة زمنيًا بحجز بين المتجاورات.

    بروتوكول البحث افتراضيًا؛ بروتوكول بنية العينة معلن الاسم ولا
    يدّعي عبور بوابة بحث («الأعداد لا تُقلص لمجرد عبور بوابة»).
    """
    raw = _read_json(candidates_path)
    from datetime import datetime

    times = [datetime.fromisoformat(t) if isinstance(t, str) else t for t in raw]
    if protocol == "research":
        protocol_config = research_protocol(embargo_s=embargo_s)
    elif protocol == "sample":
        base = dict(DEFAULT_SAMPLE_WFO_PROTOCOL)
        base["embargo_s"] = embargo_s
        protocol_config = WFOProtocolConfig.model_validate(base)
    else:
        typer.echo(f"✗ بروتوكول مجهول: {protocol} — research أو sample", err=True)
        raise typer.Exit(1)
    try:
        report = split_windows(times, protocol_config)
    except WFOProtocolError as error:
        typer.echo(f"✗ {error}", err=True)
        raise typer.Exit(1) from error
    _write_json(out_path, json.loads(report.model_dump_json()))
    typer.echo(
        f"✓ {report.protocol.protocol_name}: {len(report.windows)} نافذة تدحرج على "
        f"{report.candidates_count} مرشحًا (محجوز {report.embargoed_count}) — {out_path}"
    )


# ───────────────────────── الداخل ─────────────────────────


def _read_json(path: Path) -> list[Any]:
    with path.open(encoding="utf-8") as handle:
        data: list[Any] = json.load(handle)
        return data


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


# ───────────────────────── المرآة الحتمية D-08 (بوابة 10) ─────────────────────────


@app.command()
def mirror(
    timeframe: str = typer.Option("1m", "--timeframe", help="إطار عينة المرآة"),
    instrument: str = typer.Option("BINANCE_USDM:BTCUSDT", "--instrument", help="معرف الأداة"),
    out_path: Path = typer.Option(
        None,
        "--out",
        help="ملف تقرير المرآة (الافتراضي: docs/mirror/phase10/mirror_report.json)",
    ),
) -> None:
    """تشغيل المرآة الحتمية لأهم الأحداث ومقارنة D-08 (§10.4 + الجدول).

    منافذ Pine (نسخ مستقل من مصدر pine/) مقابل مكونات المحرك الحقيقية
    فوق العينة المرجعية — OHLCV تامة وATR ±0.01% وSweep/BOS صارمة
    وصف دلتا/POC موثق غير مشترك.
    """
    from .mirror import run_mirror

    report = run_mirror(timeframe=timeframe, instrument=instrument)
    target = out_path or (
        Path(__file__).resolve().parents[4] / "docs" / "mirror" / "phase10" / "mirror_report.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in report["rows"]:
        typer.echo(f"  {row['family']:<10} {row['status']}")
    typer.echo(f"pine-source: {report['pine_source_checks']['status']}")
    typer.echo(f"المرآة: {report['status']} — الحصيلة: {target}")
    if report["status"] != "AGREED_WITHIN_TOLERANCE":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
