"""engine-replay — مشغل الإعادة/الاختبارات (§26).

المرحلة 0: هيكل CLI فقط. المحرك الفعلي يُبنى في المرحلة 9.
"""

from __future__ import annotations

import schemas
import typer
from common.config import load_settings

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


if __name__ == "__main__":
    app()
