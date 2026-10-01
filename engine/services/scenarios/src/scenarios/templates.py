"""هوية القوالب الثلاثة (§21.2 حرفيًا) — السلاسل السببية وبناة الأطروحة.

القالب سلسلة سببية موثقة لا قاعدة تحكم جامدة («These are scenario
templates, not hard-coded universal truths» §21.2 خاتمة). كل قالب يعرف:

- **سلسلته السببية** بنص §21.2 الحرفي — تصير أطروحة السيناريو
  (``thesis`` §18.1) مع القيم الفعلية للموقع والحدث.
- **اتجاهه المشتق** من الحدث المرسي (D-04): الانعكاس ضد جهة الاجتياح،
  والاستمرار باتجاه انحياز الإطار الأعلى المؤكد، والاختراق باتجاه
  الكسر — كلها دوال صرفة حتمية قابلة للعد.
- **نوع مشغله** القابل للرصد (7.3): ``DISPLACEMENT_CONFIRM`` للانعكاس
  و``INTERNAL_BOS`` للاستمرار و``ACCEPTANCE_BEYOND``/``RETEST_HOLD``
  للاختراق بحسب مصدر الاستنساخ.
"""

from __future__ import annotations

from schemas import Direction, EventType, HTFBias, ScenarioTemplate
from schemas.liquidity import BreakAcceptEventPayload, LiquiditySide, SweepEventPayload

__all__ = [
    "TEMPLATE_CAUSAL_CHAINS",
    "anchor_event_types",
    "breakout_direction_for_break_accept",
    "breakout_direction_for_sweep",
    "breakout_trigger_kind",
    "continuation_direction_for_bias",
    "reversal_direction_for_break_accept",
    "reversal_direction_for_sweep",
    "thesis_for",
]


#: السلاسل السببية الثلاث بنص §21.2 الحرفي — قلب أطروحة كل مقترح.
TEMPLATE_CAUSAL_CHAINS: dict[ScenarioTemplate, str] = {
    ScenarioTemplate.REVERSAL: (
        "سيولة كبرى ← اجتياح ← امتصاص/إنهاك ← إزاحة ← استرجاع بنية ← إعادة اختبار/مشغل"
    ),
    ScenarioTemplate.CONTINUATION: (
        "بنية الإطار الأعلى مصطفة ← ارتداد إلى موقع موثق ← التدفق يعيد "
        "الاصطفاف ← BOS/إزاحة داخلية ← مشغل استمرار"
    ),
    ScenarioTemplate.BREAKOUT: (
        "انضغاط ← بناء سيولة ← توسع ← قبول خلف الحافة ← إعادة اختبار/استمرار"
    ),
}

#: الأحداث المرسبة المؤكدة التي ينطلق منها الاستنساخ (D-04): حدثان
#: سيوليان موقعيان حصراً — كلاهما يحمل ``zone_id`` (الربط الإلزامي
#: §10.4 شرط 5) فلا استنساخ فوق موقع غير مرسوم أبدًا.
anchor_event_types: frozenset[EventType] = frozenset(
    {
        EventType.LIQUIDITY_SWEEP_HIGH,
        EventType.LIQUIDITY_SWEEP_LOW,
        EventType.BREAK_AND_ACCEPT_HIGH,
        EventType.BREAK_AND_ACCEPT_LOW,
    }
)


# ───────────────── اشتقاق الاتجاهات من الحمولات (دوال صرفة) ─────────────────


def reversal_direction_for_sweep(payload: SweepEventPayload) -> Direction:
    """اتجاه الانعكاس من اجتياح — ضد جهة المنطقة المستهلَكة.

    اجتياح سيولة بيعية عند القيعان ثم رفض ⇒ انعكاس صاعد؛ وشرائية عند
    القمم ⇒ هابط. نفس قطبية الحدث في خريطة الدمج (الباب المؤدية إليه
    ``extract_polarity``): الحدث المسند نفسه يدعم الاتجاه المشتق.
    """
    return Direction.LONG if payload.zone_side is LiquiditySide.SELL_SIDE else Direction.SHORT


def breakout_direction_for_sweep(payload: SweepEventPayload) -> Direction:
    """اتجاه اختراقٍ يُقترح من اجتياح — فشل الرفض واستئناف الكسر.

    الاجتياح رفضُ تسلسلٍ خلف الحافة البعيدة؛ فشلُه يعني قبولًا خلفها:
    اجتياح القيعان يتحول اختراقًا هابطًا، والقمم اختراقًا صاعدًا. مشغله
    ``ACCEPTANCE_BEYOND`` القاع الحتمي المعاد اشتقاقه.
    """
    return Direction.SHORT if payload.zone_side is LiquiditySide.SELL_SIDE else Direction.LONG


def breakout_direction_for_break_accept(payload: BreakAcceptEventPayload) -> Direction:
    """اتجاه الاختراق من كسر-قبول — باتجاه القبول المؤكد.

    قبول خلف قمم (سيولة شرائية مستهلَكة بالقبول) ⇒ استمرار صاعد بإعادة
    اختبار الحافة؛ وخلف قيعان ⇒ هابط.
    """
    return Direction.LONG if payload.zone_side is LiquiditySide.BUY_SIDE else Direction.SHORT


def reversal_direction_for_break_accept(payload: BreakAcceptEventPayload) -> Direction:
    """اتجاه انعكاسٍ يُقترح من كسر-قبول — الفشل المضاد للقبول.

    القبول الذي لا يصمد = فخّ سيولة: عودة داخل المنطقة المستهلَكة
    تعكس الاتجاه. مشغله ``ZONE_RECLAIM`` للحافة البعيدة.
    """
    return Direction.SHORT if payload.zone_side is LiquiditySide.BUY_SIDE else Direction.LONG


def continuation_direction_for_bias(bias: HTFBias) -> Direction | None:
    """اتجاه الاستمرار من انحياز الإطار الأعلى — None لغير المؤكد.

    §21.2 «HTF structure aligned»: الاستمرار يُقترح فقط حين ينحاز
    الإطارُ الأعلى اتجاهًا مؤكدًا؛ الانحياز المحايد/الانتقالي/المجهول
    يعني غياب اصطفاف البنية فلا استنساخ للقالب — غياب موثق لا صمت.
    """
    if bias is HTFBias.BULLISH:
        return Direction.LONG
    if bias is HTFBias.BEARISH:
        return Direction.SHORT
    return None


def breakout_trigger_kind(event_type: EventType) -> str:
    """نوع مشغل قالب الاختراق بحسب مصدر الاستنساخ.

    من اجتياح: القبول خلف القاع الحتمي (``ACCEPTANCE_BEYOND``) —
    الحدث الأصلي رفضٌ لا قبول فينتظر المقترح قبوله الخاص. ومن كسر-قبول:
    صمود إعادة الاختبار (``RETEST_HOLD``) — القبول وقع والمشغل إتمام
    السلسلة بإعادة اختبار الحافة.
    """
    if event_type in (EventType.LIQUIDITY_SWEEP_HIGH, EventType.LIQUIDITY_SWEEP_LOW):
        return "ACCEPTANCE_BEYOND"
    if event_type in (EventType.BREAK_AND_ACCEPT_HIGH, EventType.BREAK_AND_ACCEPT_LOW):
        return "RETEST_HOLD"
    raise ValueError(f"حدث مرسِم غير معروف لمشغل الاختراق: {event_type}")


def thesis_for(template: ScenarioTemplate, *, zone_id: str, detail: str) -> str:
    """أطروحة السيناريو — السلسلة السببية §21.2 مع قيم الموقع الفعلية.

    §18.3 «Expected mechanism» يُلزم الأطروحة آلية معلنة لا شعارًا:
    السلسلة الحرفية + معرف الموقع + التفصيل الهندسي للمقترح.
    """
    return f"[{template.value}] {TEMPLATE_CAUSAL_CHAINS[template]} — الموقع {zone_id}: {detail}"
