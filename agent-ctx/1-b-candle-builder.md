# Task ID: 1-b — candle-builder (full-stack-developer)

> سجل عمل الوكيل — المهمة 1.4 من build_plan §D المرحلة 1. يمكن للوكلاء اللاحقين قراءة هذا الملف وسجل `/home/z/my-project/worklog.md` للاطلاع على أعمال السابقين.

## المهمة
منشئ الشموع الحدثي `CandleBuilder` + `bucket_floor` في `engine/services/ingestion/src/ingestion/candles.py` — شموع §8.1 كاملة الحقول المشتقة، بفصل المتطور عن المؤكد (§27 عبر is_closed)، بلا نظرة مستقبلية (§26.3)، مع اختبارات `tests/unit/test_candles.py`.

## ما أُنجز

### الملفات (ملفان فقط — التزامًا بقيد المسارات)
- `engine/services/ingestion/src/ingestion/candles.py` (370 سطرًا)
- `engine/tests/unit/test_candles.py` (751 سطرًا، 44 اختبارًا)
- commit: `493eb8f` — `feat(ingestion): المهمة 1.4 — منشئ الشموع الحدثي بميزات §8.1 وسياسة عدم إعادة الرسم §27`

### الواجهة العلنية (لمن يحتاجها من المهام اللاحقة 1.5/1.6)
- `bucket_floor(ts: datetime, timeframe: str) -> datetime` — تقريب أرضي مطلق منذ epoch للأطر `1m/5m/15m/1h/4h/1d`؛ يطبّع الواعي إلى UTC ويرفض الساذج (§7.1) ويرفع ValueError للأطر غير المدعومة.
- `SUPPORTED_TIMEFRAMES: tuple[str, ...]`
- `QUALITY_SEVERITY_LADDER: tuple[DataQuality, ...]` — الترتيب: HEALTHY < DELAYED < PARTIAL < OUT_OF_ORDER < DUPLICATED < STALE < GAP_DETECTED < UNAVAILABLE < QUARANTINED. **قابل للمراجعة عند دمج 1-a** (يخالف ترتيب تصريح enums.py في موضعي OUT_OF_ORDER/DUPLICATED — مقصود وفق تعريف المهمة، وموثق في الكود).
- `class CandleBuilder`:
  - `add_trade(event: TradeEvent, quality: DataQuality = DataQuality.HEALTHY) -> Candle | None`
    - None: أول حدث في مجرى جديد، أو حدث متأخر (يُحصى في late_events)
    - Candle(is_closed=True): الشمعة السابقة عند أول حدث يعبر حدّ دلو جديد
    - Candle(is_closed=False): نسخة المتطورة بعد تحديث تراكمي داخل الدلو
  - `close_current(instrument_id: str, timeframe: str) -> Candle | None` — إقفال صريح لنهاية البث
  - خصائص: `n_closed` / `n_evolved_updates` / `late_events` / `first_bar_time` / `last_bar_time`

### القرارات الموثقة (اتفاقيات الحواف)
1. **high == low:** body_fraction = 0.0، close_location_value = 0.5 (مختبرة حرفيًا).
2. **true_range:** أول شمعة في المجرى = high−low؛ بعدها max(high−low, |high−prev_close|, |low−prev_close|) بإغلاق آخر شمعة مقفلة في المجرى نفسه — الفجوات الزمنية لا تُتجاوز (هي جوهر TR). مختبرة بفجوة صاعدة (القمة تهيمن) وهابطة (القاع يهيمن).
3. **realized_volatility:** قيمة خام |ln(close/open)| — التطبيع بإحصاءات النظام الحديث مكانه حزمة features (مرحلة 2). القيم المتطرفة ترفضها حدود النموذج (فشل صاخب مقصود).
4. **open/close:** بترتيب وصول الأحداث لا ترتيب طوابعها (حدثية صرفة).
5. **المتأخر بعد القفل:** يُحصى في late_events، لا يعدّل المقفلة، ولا يُنشئ شمعة فائتة بأثر رجعي (حارس last_closed_bar_time لكل مجرى).
6. **instrument_id = venue:symbol** مشتق من الحدث (المفتاح الطبيعي — متسق مع فهرس ux_instruments_venue_symbol من 0.6 وfixtures schemas «BINANCE_USDM:BTCUSDT»؛ ربط UUID مسؤولية التخزين).
7. **timeframe = event.source_timeframe** — خارج الأطر الستة ValueError فورية بلا أثر جانبي.
8. **close_current(instrument_id, timeframe)** بالوسائط الصريحة — بنّاء متعدد المجاري يوجب إزالة اللبس.
9. **session_id** = تاريخ يوم bar_time بتقويم UTC بصيغة ISO YYYY-MM-DD (جلسة UTC اليومية — A-03).
10. **فخ sum() في بايثون 3.12:** الجمع المعوَّض (Neumaier) قد يخلف التراكم الحدثي اليساري بأولب واحد — الاختبار يوائم الخاصية الرياضية بapprox ويطابق التراكم اليساري تطابقًا تامًا (سلوك موثق في الاختبار).

### نتائج البوابات (حرفيًا، من جذر engine مع unset VIRTUAL_ENV)
ملفاتي (مُقاسة scoped):
- `ruff format --check candles.py test_candles.py` → `2 files already formatted`
- `ruff check candles.py test_candles.py` → `All checks passed!`
- `mypy` → صفر أخطاء في ملفاتي (ضمن 48 ملفًا مفحوصًا)
- `pytest tests/unit/test_candles.py` → `44 passed in 1.21s`
- `lint-imports` → `Contracts: 6 kept, 0 broken.`

المستودع كاملًا (أثناء عمل الوكيل الموازي 1-a):
- `ruff format --check .` → 4 ملفات للوكيل الموازي غير منسقة (binance.py, quality.py, test_binance_adapter.py, test_refine.py)
- `ruff check .` → 6 أخطاء كلها في ملفاته (test_binance_live.py, test_refine.py)
- `mypy` → 3 أخطاء كلها في ملفاته (refine.py, test_binance_adapter.py)
- `pytest` → 3 failed (كلها ملفاته) + 339 passed (تشمل 44 الخاصة بي) + 5 deselected
- أعدت المحاولة مرتين بعد انتظار (100s و150s) والوكيل ما يزال يكتب ملفات جديدة — الفشل ليس من عمل هذه المهمة وموثق.

## ما لم يُمس (التزامًا بالقيود)
`__init__.py` للحزمة، `pyproject.toml` (للمستودع وللحزمة)، uv.lock، وكل ملفات الوكيل الموازي (binance.py/refine.py/quality.py واختباراتها).
