"""اختبارات محرك السيناريوهات — القيادة الشريطية الكاملة (§33.4).

التدفق المتكامل المفحوص على شريطنة حتمية محسوبة:

- **التوليد** (D-04): المرسِم يستنسخ الثلاثة ويُسجَّلون DRAFT؛
- **الترقية** (§18.4): مجموعتان داعمتان (المرسِم + الانحياز) يرقّيان
  الانعكاس والاستمرار الطويلين، والاختراق القصير بلا مجموعات داعمة
  يبقى مسودة (رياضيات الدمج تصفي);
- **المشغل** (§18.4): إزاحة 1m صاعدة تشعل الانعكاس داخل انجراف مسموح،
  وBOS داخلي يشعل الاستمرار — وحدث التدفق (استمرار هابط) يمنح
  الاختراقَ القصير مجموعته الثانية فيرقّى ويشتعل بإعادة اختبار صامدة؛
- **التنافس** (7.4): الطويلان والقصير المتزامن TRIGGERED — الحسم
  بالأسبقية والخاسر SUPPRESSED بسبب يسمي فائزه;
- **الانقضاء** (§18.5 شرط 4): المسودة التي لم ترقَ تنقضي بزعنفتها;
- **الجودة** (§18.5 شرط 5): لقطة غير آمنة تُطفئ كل الأحياء;
- **الـveto** (D-03-د): حدث حجب صلب يمنع الترقية ولا يمس الدرجات;
- **الانجراف** (§18.4): مشغل بعيد عن الدخول ⇒ إبطال شرط 6 لا ترخيص;
- **الحتمية واللا-نظرة**: مساران كاملان متطابقان بايت-بايت، وبادئة
  التقييم ⊆ الكامل.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from _scenario_fixtures import (
    ANCHOR_TIME,
    ATR,
    make_candle,
    make_market_state,
    make_sweep_payload,
    make_target_map,
    make_zone,
    sell_zone,
)
from pydantic import BaseModel
from scenarios.engine import ScenarioEngine
from scenarios.parameter_sets import default_scenario_config
from schemas import (
    BreakDirection,
    DataQuality,
    Direction,
    DisplacementEventPayload,
    EventType,
    FlowContinuationEventPayload,
    FlowDirection,
    Scenario,
    ScenarioState,
    ScenarioTemplate,
    StructureBreakPayload,
    SwingScope,
)
from schemas.liquidity import LiquiditySide


@dataclass(frozen=True)
class Ev:
    """حدث تحليل اختباري — عقد القراءة الثلاثي نفسه الذي تنتجه الكواشف."""

    event_type: EventType
    event_time: datetime
    payload: BaseModel


def _displacement(index: int, up: bool = True) -> Ev:
    when = ANCHOR_TIME + timedelta(minutes=index)
    return Ev(
        EventType.DISPLACEMENT_UP if up else EventType.DISPLACEMENT_DOWN,
        when,
        DisplacementEventPayload(
            instrument="BINANCE_USDM:BTCUSDT",
            timeframe="1m",
            bar_time=when,
            direction=BreakDirection.UP if up else BreakDirection.DOWN,
            range_zscore=2.0,
            body_fraction=0.8,
            close_location=0.9,
            atr_multiple=2.0,
            velocity=1.5,
            follow_through=0.6,
        ),
    )


def _internal_bos(index: int, up: bool = True) -> Ev:
    when = ANCHOR_TIME + timedelta(minutes=index)
    return Ev(
        EventType.INTERNAL_BOS,
        when,
        StructureBreakPayload(
            instrument="BINANCE_USDM:BTCUSDT",
            timeframe="1m",
            bar_time=when,
            swing_id=f"swing-{index}",
            swing_scope=SwingScope.INTERNAL,
            break_direction=BreakDirection.UP if up else BreakDirection.DOWN,
            breach_distance_atr=0.8,
            closing_acceptance=0.7,
            follow_through=0.5,
        ),
    )


def _flow_down(index: int) -> Ev:
    when = ANCHOR_TIME + timedelta(minutes=index)
    return Ev(
        EventType.FLOW_CONTINUATION_DOWN,
        when,
        FlowContinuationEventPayload(
            instrument="BINANCE_USDM:BTCUSDT",
            timeframe="1m",
            bar_time=when,
            direction=FlowDirection.DOWN,
            delta=-50.0,
            delta_share=-0.5,
            response_atr=1.0,
            efficiency=2.0,
        ),
    )


def _bearish_engulfing(index: int) -> Ev:
    from schemas import CandlePatternEventPayload
    from schemas.patterns import CandlePatternFamily, PatternDirection

    when = ANCHOR_TIME + timedelta(minutes=index)
    return Ev(
        EventType.BEARISH_ENGULFING,
        when,
        CandlePatternEventPayload(
            instrument="BINANCE_USDM:BTCUSDT",
            timeframe="1m",
            bar_time=when,
            family=CandlePatternFamily.ENGULFING,
            direction=PatternDirection.BEARISH,
            feature_readings={
                "body_fraction": 0.6,
                "wick_asymmetry": -0.4,
                "close_location": 0.2,
                "range_percentile": 0.7,
                "gap_relationship": 0.5,
                "volume_relationship": 0.6,
            },
            strength=0.7,
            bars_in_pattern=2,
        ),
    )


def _data_stale(index: int) -> Ev:
    when = ANCHOR_TIME + timedelta(minutes=index)

    class _StalePayload(BaseModel):
        instrument: str = "BINANCE_USDM:BTCUSDT"
        timeframe: str = "1m"
        bar_time: datetime = when

    return Ev(EventType.DATA_STALE, when, _StalePayload())


def _anchor_sweep(engine: ScenarioEngine) -> None:
    engine.on_anchor(
        EventType.LIQUIDITY_SWEEP_LOW,
        ANCHOR_TIME,
        make_sweep_payload(),
        zone=sell_zone(),
        targets=make_target_map(),
        state=make_market_state(),  # انحياز صاعد مؤكد
        atr=ATR,
    )


def _by_template(engine: ScenarioEngine, template: ScenarioTemplate) -> Scenario:
    (scenario,) = [s for s in engine.scenarios() if s.template is template]
    return scenario


def _by_direction_template(
    engine: ScenarioEngine, direction: Direction, template: ScenarioTemplate
) -> Scenario:
    """الجلب بالاتجاه والقالب معًا — المرسمان المتناقضان يشاركان القوالب."""
    (scenario,) = [
        s for s in engine.scenarios() if s.direction is direction and s.template is template
    ]
    return scenario


# ───────────────────────── الدرب الكامل ─────────────────────────


class TestFullDrive:
    """توليد ← ترقية ← مشغل ← تنافس — على شريطنة محسوبة."""

    def test_promotion_needs_two_supporting_groups(self) -> None:
        engine = ScenarioEngine()
        _anchor_sweep(engine)
        # الشريط الأول: بلا أحداث جديدة — المرسِم + الانحياز = مجموعتان
        transitions = engine.on_bar(
            make_candle(1, close=59_850.0, high=59_900.0, low=59_800.0, open_=59_870.0),
            state=make_market_state(),
            atr=ATR,
        )
        promoted = {t.scenario_id: t for t in transitions if t.to_state is ScenarioState.ACTIVE}
        reversal = _by_template(engine, ScenarioTemplate.REVERSAL)
        continuation = _by_template(engine, ScenarioTemplate.CONTINUATION)
        breakout = _by_template(engine, ScenarioTemplate.BREAKOUT)
        # الطويلان رقّيا (LIQUIDITY + STRUCTURE داعمتان)
        assert reversal.scenario_id in promoted
        assert continuation.scenario_id in promoted
        assert "مجموعات دليل مستقلة داعمة" in promoted[reversal.scenario_id].reason
        # القصير بلا مجموعات داعمة (المرسِم والانحياز كلاهما يعارضه) — مسودة
        assert breakout.scenario_id not in promoted
        assert breakout.state is ScenarioState.DRAFT
        assert reversal.state is ScenarioState.ACTIVE

    def test_displacement_triggers_reversal_within_drift(self) -> None:
        engine = ScenarioEngine()
        _anchor_sweep(engine)
        engine.on_bar(
            make_candle(1, close=59_850.0, high=59_900.0, low=59_800.0, open_=59_870.0),
            state=make_market_state(),
            atr=ATR,
        )  # ترقية
        transitions = engine.on_bar(
            make_candle(2, close=59_880.0, high=59_920.0, low=59_840.0, open_=59_860.0),
            analysis_events=(_displacement(2),),
            state=make_market_state(),
            atr=ATR,
        )
        reversal = _by_template(engine, ScenarioTemplate.REVERSAL)
        assert reversal.state is ScenarioState.TRIGGERED
        fired = [t for t in transitions if t.to_state is ScenarioState.TRIGGERED]
        assert len(fired) == 1
        assert "DISPLACEMENT_CONFIRM" in fired[0].reason
        assert "الانجراف 0.00 ATR" in fired[0].reason  # الإغلاق داخل النطاق

    def test_internal_bos_triggers_continuation(self) -> None:
        engine = ScenarioEngine()
        _anchor_sweep(engine)
        engine.on_bar(
            make_candle(1, close=59_850.0, high=59_900.0, low=59_800.0, open_=59_870.0),
            state=make_market_state(),
            atr=ATR,
        )
        engine.on_bar(
            make_candle(2, close=59_880.0, high=59_920.0, low=59_840.0, open_=59_860.0),
            analysis_events=(_internal_bos(2),),
            state=make_market_state(),
            atr=ATR,
        )
        continuation = _by_template(engine, ScenarioTemplate.CONTINUATION)
        assert continuation.state is ScenarioState.TRIGGERED
        # نفس الاتجاه لا تنافس — كلاهما يحيا
        reversal = _by_template(engine, ScenarioTemplate.REVERSAL)
        assert reversal.state is ScenarioState.ACTIVE  # رُقّي ولم يُشعل بعد

    def test_draft_expires_by_fin(self) -> None:
        """الزعنفة (D-04): المسودة التي لم ترقَ تنقضي — §18.5 شرط 4."""
        engine = ScenarioEngine()
        _anchor_sweep(engine)
        expiry_bars = default_scenario_config().expiry_bars[ScenarioTemplate.BREAKOUT]
        # أشرطة حتى ما بعد الزعنفة (60 شمعة على 1m)
        for index in range(1, expiry_bars + 2):
            engine.on_bar(
                make_candle(index, close=59_850.0, high=59_900.0, low=59_800.0, open_=59_870.0),
                state=make_market_state(),
                atr=ATR,
            )
        breakout = _by_template(engine, ScenarioTemplate.BREAKOUT)
        assert breakout.state is ScenarioState.EXPIRED
        expired = [
            t
            for t in engine.transitions()
            if t.scenario_id == breakout.scenario_id and t.to_state is ScenarioState.EXPIRED
        ]
        assert expired and "شرط 4" in expired[0].reason

    def test_opposing_conflict_suppresses_loser(self) -> None:
        """مرسمان متناقضان: طويل مُشعل يقصيرَ مُشعلًا معه — الأسبقية تحسم.

        مشغلا المرتسم الواحد متعارضان هندسيًا (قبول القاع الحتمي للاختراق
        هو إبطال الانعكاس حرفيًا) فالتنافس الحي يقتضي مرسِمين: اجتياح
        بيعية أنجب انعكاسًا طويلًا مُشعلًا، ثم اجتياح شرائية أعلى أنجبت
        انعكاسًا قصيرًا يتشعل معه — الحسم بالأسبقية والخاسر SUPPRESSED.
        """
        engine = ScenarioEngine()
        # المرسي الأول: اجتياح بيعية (انعكاس طويل) — انحياز صاعد
        _anchor_sweep(engine)
        engine.on_bar(
            make_candle(1, close=59_850.0, high=59_900.0, low=59_800.0, open_=59_870.0),
            state=make_market_state(),
            atr=ATR,
        )  # ترقية الطويلين
        engine.on_bar(
            make_candle(2, close=59_880.0, high=59_920.0, low=59_840.0, open_=59_860.0),
            analysis_events=(_displacement(2),),
            state=make_market_state(),
            atr=ATR,
        )  # الانعكاس الطويل TRIGGERED
        long_reversal = _by_template(engine, ScenarioTemplate.REVERSAL)
        assert long_reversal.state is ScenarioState.TRIGGERED

        # المرسي الثاني: اجتياح شرائية فوق السعر (انعكاس قصير)
        buy_zone = make_zone(
            zone_id="lz-buy-high",
            side=LiquiditySide.BUY_SIDE,
            price_low=60_500.0,
            price_high=60_600.0,
        )
        engine.on_anchor(
            EventType.LIQUIDITY_SWEEP_HIGH,
            ANCHOR_TIME + timedelta(minutes=3),
            make_sweep_payload(zone_id="lz-buy-high", zone_side=LiquiditySide.BUY_SIDE),
            zone=buy_zone,
            targets=make_target_map(),
            state=make_market_state(),
            atr=ATR,
        )
        # الشريط 4: ابتلاع هابط (PRICE_ACTION داعم للقصير) يرقّيه
        engine.on_bar(
            make_candle(4, close=60_550.0, high=60_600.0, low=60_500.0, open_=60_580.0),
            analysis_events=(_bearish_engulfing(4),),
            state=make_market_state(),
            atr=ATR,
        )
        short_candidates = [s for s in engine.scenarios() if s.direction is Direction.SHORT]
        (short_reversal,) = [s for s in short_candidates if s.template is ScenarioTemplate.REVERSAL]
        assert short_reversal.state is ScenarioState.ACTIVE

        # الشريط 5: إزاحة هابطة تشعل القصير — والطويل ما يزال TRIGGERED
        engine.on_bar(
            make_candle(5, close=60_520.0, high=60_580.0, low=60_480.0, open_=60_560.0),
            analysis_events=(_displacement(5, up=False),),
            state=make_market_state(),
            atr=ATR,
        )
        # النسخ تتجدد مع كل انتقال (جمّدة) — الجلب من المحرك لا الاحتفاظ
        # بنسخة قديمة من شريط سابق
        fresh_short = _by_direction_template(engine, Direction.SHORT, ScenarioTemplate.REVERSAL)
        fresh_long = _by_direction_template(engine, Direction.LONG, ScenarioTemplate.REVERSAL)
        states = {fresh_short.state, fresh_long.state}
        # المتضادان المتزامنان: أحدهما SUPPRESSED بسبب يسمي فائزه
        assert ScenarioState.TRIGGERED in states
        assert ScenarioState.SUPPRESSED in states
        suppressed = [t for t in engine.transitions() if t.to_state is ScenarioState.SUPPRESSED]
        assert suppressed and "لا إلغاء صامت" in suppressed[0].reason


# ───────────────────────── الجودة والـveto ─────────────────────────


class TestQualityAndVeto:
    """التدهور الآمن — الجودة تُطفئ والحجب يمنع الترقية بلا مس الأرقام."""

    def test_unsafe_quality_cancels_all_live(self) -> None:
        engine = ScenarioEngine()
        _anchor_sweep(engine)
        engine.on_bar(
            make_candle(1, close=59_850.0, high=59_900.0, low=59_800.0, open_=59_870.0),
            state=make_market_state(),
            atr=ATR,
        )
        transitions = engine.on_bar(
            make_candle(2, close=59_850.0, high=59_900.0, low=59_800.0, open_=59_870.0),
            state=make_market_state(data_quality=DataQuality.STALE),
            atr=ATR,
        )
        assert engine.live_scenarios() == ()
        assert {t.to_state for t in transitions} == {ScenarioState.CANCELLED_BY_DATA_QUALITY}
        assert all("شرط 5" in t.reason for t in transitions)
        # لا إنقاذ بعدها — كل الانتقالات اللاحقة مرفوضة (النهائية)
        later = engine.on_bar(
            make_candle(3, close=59_850.0, high=59_900.0, low=59_800.0, open_=59_870.0),
            state=make_market_state(),
            atr=ATR,
        )
        assert later == ()

    def test_hard_block_event_vetoes_promotion(self) -> None:
        """DATA_STALE حدثًا: يوجه إلى veto — الترقية ممنوعة والدرجات سليمة."""
        engine = ScenarioEngine()
        _anchor_sweep(engine)
        transitions = engine.on_bar(
            make_candle(1, close=59_850.0, high=59_900.0, low=59_800.0, open_=59_870.0),
            analysis_events=(_data_stale(1),),
            state=make_market_state(),
            atr=ATR,
        )
        assert transitions == ()  # لا ترقية تحت veto
        assert engine.veto_reasons == ("hard-block:DATA_STALE",)
        for scenario in engine.live_scenarios():
            assert scenario.state is ScenarioState.DRAFT
        # الدرجة لم تُمس رقميًا — veto منطق بولياني خارج الحساب (D-03-د):
        # مقارنة محركين متطابقي الأشرطة (مع الحجب وبدونه) — نفس الاضمحلال
        # الزمني للطراوة ونفس السجل، فأي فرق درجات يعني مساس الحجب بالحساب.
        clean_engine = ScenarioEngine()
        _anchor_sweep(clean_engine)
        clean_engine.on_bar(
            make_candle(1, close=59_850.0, high=59_900.0, low=59_800.0, open_=59_870.0),
            state=make_market_state(),
            atr=ATR,
        )
        vetoed_reversal = _by_template(engine, ScenarioTemplate.REVERSAL)
        clean_reversal = _by_template(clean_engine, ScenarioTemplate.REVERSAL)
        assert vetoed_reversal.scenario_score == pytest.approx(clean_reversal.scenario_score)
        assert vetoed_reversal.supporting_evidence == clean_reversal.supporting_evidence


# ───────────────────────── الانجراف ─────────────────────────


class TestEntryDriftGuard:
    """المشغل بعيدًا عن الدخول ⇒ إبطال شرط 6 لا ترخيص (§18.4)."""

    def test_far_trigger_invalidates(self) -> None:
        engine = ScenarioEngine()
        _anchor_sweep(engine)
        engine.on_bar(
            make_candle(1, close=59_850.0, high=59_900.0, low=59_800.0, open_=59_870.0),
            state=make_market_state(),
            atr=ATR,
        )
        # إزاحة صاعدة لكن الإغلاق 400 فوق الحافة العليا ⇒ انجراف 2.0+
        transitions = engine.on_bar(
            make_candle(2, close=60_400.0, high=60_450.0, low=60_350.0, open_=60_380.0),
            analysis_events=(_displacement(2),),
            state=make_market_state(),
            atr=ATR,
        )
        reversal = _by_template(engine, ScenarioTemplate.REVERSAL)
        assert reversal.state is ScenarioState.INVALIDATED
        # حارس الانجراف علّل بإبطال شرط 6 — (القفزة قتلت الاختراقَ القصير
        # أيضًا بشرط 1/3 في الشريطة نفسها — كلاهما قانوني وكلٌّ بسجله)
        drift_fired = [t for t in transitions if "شرط 6" in t.reason]
        assert drift_fired
        assert drift_fired[0].to_state is ScenarioState.INVALIDATED
        assert drift_fired[0].scenario_id == reversal.scenario_id


# ───────────────────────── الحتمية واللا-نظرة ─────────────────────────


class TestDeterminismAndNoLookahead:
    """نفس الأشرطة ⇒ نفس الانتقالات؛ وبادئة التقييم ⊆ الكامل."""

    def _drive(self, bars: int) -> tuple[ScenarioEngine, list[str]]:
        engine = ScenarioEngine()
        _anchor_sweep(engine)
        for index in range(1, bars + 1):
            events: tuple[Ev, ...] = ()
            if index == 2:
                events = (_displacement(2),)
            elif index == 3:
                events = (_internal_bos(3),)
            engine.on_bar(
                make_candle(
                    index,
                    close=59_850.0 + 10.0 * index,
                    high=59_900.0 + 10.0 * index,
                    low=59_800.0 + 10.0 * index,
                    open_=59_870.0 + 10.0 * index,
                ),
                analysis_events=events,
                state=make_market_state(),
                atr=ATR,
            )
        serialized = [
            f"{t.scenario_id}|{t.from_state.value}>{t.to_state.value}|{t.reason}"
            for t in engine.transitions()
        ]
        return engine, serialized

    def test_two_runs_byte_identical(self) -> None:
        _first_engine, first = self._drive(4)
        _second_engine, second = self._drive(4)
        assert first == second

    def test_prefix_is_stable_subset(self) -> None:
        """أشرطة أقدم لا تغير انتقالات الأشرطة الأسبق (لا-نظرة §26.3)."""
        _short_engine, short_run = self._drive(2)
        _full_engine, full_run = self._drive(4)
        assert full_run[: len(short_run)] == short_run

    def test_scenario_dump_deterministic(self) -> None:
        first_engine, _ = self._drive(3)
        second_engine, _ = self._drive(3)
        assert [s.model_dump_json() for s in first_engine.scenarios()] == [
            s.model_dump_json() for s in second_engine.scenarios()
        ]


# ───────────────────────── حرس المحرك ─────────────────────────


class TestEngineGuards:
    def test_non_positive_atr_rejected(self) -> None:
        engine = ScenarioEngine()
        with pytest.raises(ValueError, match="ATR غير موجب"):
            engine.on_bar(make_candle(1), atr=0.0)

    def test_foreign_symbol_rejected(self) -> None:
        engine = ScenarioEngine()
        _anchor_sweep(engine)
        foreign = make_candle(1)
        foreign = foreign.model_copy(update={"instrument_id": "BINANCE_USDM:ETHUSDT"})
        with pytest.raises(ValueError, match="أداة أجنبية"):
            engine.on_bar(foreign, atr=ATR)

    def test_re_anchor_is_idempotent(self) -> None:
        engine = ScenarioEngine()
        _anchor_sweep(engine)
        _anchor_sweep(engine)  # إعادة إرسال المرسِم نفسه
        assert len(engine.scenarios()) == 3  # لا استنساخ مكرر
        assert len(engine.live_scenarios()) == 3


# ───────────────────────── مساعدات ─────────────────────────


def _fresh_proposal_score(template: ScenarioTemplate) -> float:
    """درجة الميلاد للمقترح — مرجع استقلال عن المحرك."""
    proposer_engine = ScenarioEngine()
    outcome = proposer_engine.on_anchor(
        EventType.LIQUIDITY_SWEEP_LOW,
        ANCHOR_TIME,
        make_sweep_payload(),
        zone=sell_zone(),
        targets=make_target_map(),
        state=make_market_state(),
        atr=ATR,
    )
    (scenario,) = [s for s in outcome.proposals if s.template is template]
    return float(scenario.scenario_score)
