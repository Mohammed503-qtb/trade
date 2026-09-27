"""اختبارات خصائص التأسيس — تثبت الثوابت البنيوية (§38.2) من اليوم الأول."""

from __future__ import annotations

from common.config import Settings
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st


class TestSettingsImmutability:
    """الإعدادات كائن مجمّد — أي محاولة تعديل تُرفض (منع الحالة القابلة للعبث)."""

    @given(value=st.text(min_size=1, max_size=64))
    @hyp_settings(max_examples=25)
    def test_settings_reject_mutation(self, value: str) -> None:
        import pytest
        from pydantic import ValidationError

        s = Settings(_env_file=None)
        with pytest.raises((ValidationError, TypeError)):
            s.engine_env = value  # type: ignore[misc]


class TestTimeframeDefaults:
    """أزمنة الأطر المعرّفة إعداديًا لا تُقبل قيمًا فارغة."""

    @given(tf=st.sampled_from(["1m", "5m", "15m", "1h", "4h", "1d"]))
    @hyp_settings(max_examples=20)
    def test_valid_timeframes_parse(self, tf: str) -> None:
        s = Settings(_env_file=None, ENGINE_TIMEFRAME_HTF=tf)
        assert s.engine_timeframe_htf == tf
