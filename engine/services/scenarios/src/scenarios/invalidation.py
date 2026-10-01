"""الإبطال الفوري (§18.5 + §23.4) — مقيّم حتمي من المدخلات المرصودة.

«Immediate invalidation occurs when» — الشروط الست بمقيّس واحد يرجع
سبب الإبطال أو ``None``:

1. **الإبطال البنيوي الصريح** و3. **القبول عبر منطقة الإبطال** — شرطان
   يعالجهما فحص سعري واحد بجواب ``InvalidationRule`` نفسها:
   ``accept_through=True`` يقتضي إغلاقًا عبر المستوى بالعازلة (فتيل
   لا يكفي)، و``False`` يكفيه اللمس — عقد الحقل منذ المرحلة 0.
2. **فشل حدث السيولة الذي تشترطه الأطروحة بالاتجاه المعاكس** — كسر-قبول
   على منطقة المرسِم نفسها: رفضُ الاجتياح مات رسميًا حين تقبل السوق
   خلف منطقته (المنطقة CONSUMED — حكم كاشف السيولة لا إعادة اشتقاق).
4. **انقضاء التوقيت المتوقع** — عمر الزعنفة (D-04)؛ يفحصه المحرك عند
   شريطته (``expiry_time`` حقل السيناريو) فيمرر نتيجته هنا للاحتواء
   الكامل للأسباب الستة بمكان واحد.
5. **جودة بيانات غير آمنة** — يفحصه المحرك من لقطة الحالة (فقط
   HEALTHY وDELAYED يصلان معالجة القرار §7.4) ويمرر نتيجته كذلك.
6. **ظروف تنفيذ مختلفة بنيويًا** — حارس انجراف الدخول §18.4 (المسافة
   من إغلاق شمعة المشغل إلى منطقة الدخول > ``max_entry_drift_atr``):
   المشغل رُصد لكن الدخول الفعلي صار رديئًا فالسيناريو يُبطَل لا
   يُرخَّص. الجزء المكلف (reward/risk بعد التكاليف §25.2) مرحلة 8.

«The scenario cannot be "rescued" by inventing new evidence after
invalidation» — المقيّم لا يعرف إنقاذًا: سبب الإبطال حكم نهائي،
وآلة الحياة تحرّم الخروج من INVALIDATED أصلًا (lifecycle).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NamedTuple

from schemas import (
    Candle,
    Direction,
    EventType,
    Scenario,
    ScenarioState,
    ScenarioTemplate,
)

__all__ = ["InvalidationEvaluator", "InvalidationVerdict", "entry_drift_atr"]


class InvalidationVerdict(NamedTuple):
    """حكم إبطال منظّم — الحالة الهدف (§18.2) مع سببها المعلّل.

    النهايات البديلة ثلاث متمايزة: الإبطال البنيوي INVALIDATED والانقضاء
    EXPIRED والإلغاء بالجودة CANCELLED_BY_DATA_QUALITY — الخلط بينها
    يطمس دورة الحياة القابلة للتدقيق (§31.3).
    """

    state: ScenarioState
    reason: str


def entry_drift_atr(scenario: Scenario, close: float, atr: float) -> float:
    """انجراف الدخول §18.4 — مسافة الإغلاق عن منطقة الدخول مقاسة بـATR.

    مسافة غير سالبة إلى أقرب حافة النطاق: داخل النطاق صفر، وخارجه
    بعدها بالإغلاق. «moved too far from the planned entry» يقاس على
    الإغلاق لا الفتيل — قرار تنفيذٍ يُتخذ على إغلاق.
    """
    if atr <= 0.0:
        raise ValueError(f"ATR غير موجب: {atr} — مقياس الانجراف النسبي")
    low = float(scenario.entry_zone.price_low)
    high = float(scenario.entry_zone.price_high)
    if close < low:
        return (low - close) / atr
    if close > high:
        return (close - high) / atr
    return 0.0


class InvalidationEvaluator:
    """مقيّم إبطال حتمي — من السيناريو والشريط والأحداث المرصودة فقط.

    لا ساعة ولا حالة: ``candle`` شمعة إطار التنفيذ المغلقة و``events``
    أحداثها المؤكدة (كسر-قبول بالحمولة السيولية). الشروط الزمنية
    (الانقضاء) والبيئية (الجودة) يمررها المحركُ مبينا لأن مصدرهما
    اللقطة والزعنفة لا الشمعة.
    """

    def __init__(self, max_entry_drift_atr: float) -> None:
        if max_entry_drift_atr <= 0.0:
            raise ValueError(f"سقف انجراف غير موجب: {max_entry_drift_atr}")
        self._max_drift = max_entry_drift_atr

    @property
    def max_entry_drift_atr(self) -> float:
        """سقف الانجراف المسموح — من الإعداد المجمّد."""
        return self._max_drift

    def check(
        self,
        scenario: Scenario,
        *,
        candle: Candle,
        events: Sequence[tuple[EventType, Any]] = (),
        expired: bool = False,
        data_quality_unsafe: bool = False,
        entry_drift_exceeded: bool = False,
    ) -> InvalidationVerdict | None:
        """حكم الإبطال الفوري أو ``None`` — بالأولوية الموثقة أدناه.

        الترتيب (حتمي موثق): ظروف التنفيذ ثم الحدث المعاكس ثم القبول
        السعري ثم الانقضاء ثم الجودة — الأسباب الأشد صلة بالقرار
        الفوري أولًا، والسبب الواحد يكفي (أول محدد يرجع). كل سبب يحمل
        حالته الهدف من نهايات §18.2 البديلة الثلاث.
        """
        # (6) ظروف تنفيذ مختلفة بنيويًا — حارس انجراف الدخول §18.4.
        if entry_drift_exceeded:
            return InvalidationVerdict(
                ScenarioState.INVALIDATED,
                "ظروف تنفيذ مختلفة بنيويًا (§18.5 شرط 6): المشغل رُصد والإغلاق "
                "بعيد عن منطقة الدخول بأكثر من "
                f"{self._max_drift:.2f} ATR — قرار الدخول رديء التنفيذ فيُبطَل "
                "لا يُرخَّص (الجزء المكلف §25.2 موثق مؤجل للمرحلة 8)",
            )

        # (2) فشل حدث السيولة المشروط بالاتجاه المعاكس — كسر-قبول على
        # منطقة المرسِم: فرضية الرفض ماتت بقبول رسمي خلفها. يسري على
        # الأطروحات المشروطة بصمود الرفض/الموقع حصرًا (انظر
        # ``_rejection_dependent``): الانعكاس دائما والاستمرار من اجتياح
        # — أما الاختراق فأطروحته القبول نفسه فالحادث تأكيد له لا فشل،
        # والاستمرار من قبول فموضعه حافة القبول لا المنطقة.
        if self._rejection_dependent(scenario):
            anchor_zone = self._anchor_zone_id(scenario)
            if anchor_zone is not None:
                for event_type, payload in events:
                    if event_type not in (
                        EventType.BREAK_AND_ACCEPT_HIGH,
                        EventType.BREAK_AND_ACCEPT_LOW,
                    ):
                        continue
                    if self._payload_zone_id(payload) == anchor_zone:
                        return InvalidationVerdict(
                            ScenarioState.INVALIDATED,
                            "حدث السيولة المشروط بالأطروحة فشل بالاتجاه المعاكس "
                            f"(§18.5 شرط 2): كسر-قبول على منطقة المرسِم {anchor_zone} — "
                            "فرضية الرفض ماتت بقبول رسمي خلف المنطقة",
                        )

        # (1)+(3) الإبطال البنيوي الصريح / القبول عبر منطقة الإبطال —
        # إغلاق (أو لمس عند accept_through=False) عبر المستوى بالعازلة.
        rule = scenario.invalidation
        level = float(rule.structural_level)
        buffer = float(rule.volatility_buffer)
        if scenario.direction is Direction.LONG:
            breach_price = candle.close if rule.accept_through else candle.low
            if breach_price < level - buffer:
                how = "إغلاق" if rule.accept_through else "لمس"
                return InvalidationVerdict(
                    ScenarioState.INVALIDATED,
                    f"قبول {how} عبر منطقة الإبطال (§18.5 شرط 1/3): "
                    f"{breach_price:.2f} دون المستوى البنيوي {level:.2f} بعازلة "
                    f"{buffer:.2f}",
                )
        else:
            breach_price = candle.close if rule.accept_through else candle.high
            if breach_price > level + buffer:
                how = "إغلاق" if rule.accept_through else "لمس"
                return InvalidationVerdict(
                    ScenarioState.INVALIDATED,
                    f"قبول {how} عبر منطقة الإبطال (§18.5 شرط 1/3): "
                    f"{breach_price:.2f} فوق المستوى البنيوي {level:.2f} بعازلة "
                    f"{buffer:.2f}",
                )

        # (4) انقضاء التوقيت المتوقع — عمر الزعنفة (D-04) — حالة EXPIRED
        # المتخصصة (§18.2 نهاية بديلة قائمة بذاتها لا صورة من الإبطال).
        if expired:
            return InvalidationVerdict(
                ScenarioState.EXPIRED,
                "انقضاء التوقيت المتوقع (§18.5 شرط 4): عمر الزعنفة الزمنية "
                "للمقترح بلغ نهايته بلا مشغل",
            )

        # (5) جودة بيانات غير آمنة — إلغاء متخصص (§18.2 نهاية بديلة قائمة بذاتها).
        if data_quality_unsafe:
            return InvalidationVerdict(
                ScenarioState.CANCELLED_BY_DATA_QUALITY,
                "جودة بيانات غير آمنة (§18.5 شرط 5): فقط HEALTHY وDELAYED "
                "يصلان معالجة القرار (§7.4)",
            )

        return None

    # ───────────────────────── مساعدات ─────────────────────────

    @staticmethod
    def _rejection_dependent(scenario: Scenario) -> bool:
        """هل تشترط الأطروحة صمود الرفض/الموقع؟ — نطاق الشرط 2 (§18.5).

        الانعكاس دائما (رفض الاجتياح أو فشل القبول)، والاستمرار من
        اجتياح فقط (الموقع الذي يُرتد إليه) — أما الاختراق فأطروحته
        القبول نفسه، والاستمرار من قبول فموضعه حافة القبول لا المنطقة.
        """
        if scenario.template is ScenarioTemplate.REVERSAL:
            return True
        if scenario.template is ScenarioTemplate.CONTINUATION:
            anchor_type = str(scenario.location_snapshot.get("anchor_event_type", ""))
            return anchor_type in ("LIQUIDITY_SWEEP_HIGH", "LIQUIDITY_SWEEP_LOW")
        return False

    @staticmethod
    def _anchor_zone_id(scenario: Scenario) -> str | None:
        """منطقة المرسِم من لقطة الموقع — None لغياب المفتاح الموثق."""
        zone = scenario.location_snapshot.get("zone")
        if isinstance(zone, dict):
            zone_id = zone.get("zone_id")
            if isinstance(zone_id, str):
                return zone_id
        return None

    @staticmethod
    def _payload_zone_id(payload: Any) -> str | None:
        """zone_id من حمولة كسر-قبول — بنية الحمولة السيولية الموثقة."""
        if hasattr(payload, "zone_id"):
            value = payload.zone_id
            if isinstance(value, str):
                return value
        if isinstance(payload, dict):
            value = payload.get("zone_id")
            if isinstance(value, str):
                return value
        return None
