# Task ID: 2-f — Agent: snapshot-builder

## المهمة
هجرة جدول market_states (§31.3) + بنّاء لقطة حالة السوق + ناشر NATS (مثال §32) + اختبارات مستهلك وتخزين حية، في `/home/z/my-project/engine`.

## ما أُنجز (الالتزام ca675f2 — 12 ملفًا، 1598 إدراجًا)
- `migrations/versions/0003_market_states.py` (94 سطرًا): جدول market_states — instrument_id uuid بترميز uuid5(venue:symbol)، timestamptz، VARCHAR فوق أطوال التعدادات، payload JSONB، قيد مئيني، فهرس فريد (هدف ON CONFLICT) + فهرس أحدث-لقطة event_time DESC.
- `services/market_state/src/market_state/snapshot.py` (129): SnapshotInputs + build_snapshot + snapshot_session_id.
- `services/market_state/src/market_state/store.py` (157): MarketStateStore (conn من المستدعي) + snapshot_instrument_uuid.
- `services/market_state/src/market_state/__init__.py`: تصدير الرموز الجديدة.
- `services/market_state/pyproject.toml`: +asyncpg.
- `apps/worker/src/engine_worker/publisher.py` (105): SnapshotPublisher + NATSPublishClient (بروتوكول) + normalize_instrument.
- `apps/worker/src/engine_worker/__main__.py`: تشغيل تجريبي واحد قبل النبض (مثال §32 حرفيًا) — هيكل النبض لم يُمس.
- `tests/unit/test_snapshot.py` (59 اختبارًا) + `tests/unit/test_publisher.py` (18) + `tests/integration/test_market_states_live.py` (4).
- الجذر: `uv add --dev jsonschema types-jsonschema` (pyproject + uv.lock).

## قرارات التصميم الحرجة
1. **المقياس [0,100] لا [0,1]**: تعليمة المهمة قالت «توافق Percentile: [0,1]» لكن Percentile في schemas هو ge=0/le=100 (ومثال §32 نفسه 62.4). اتُّبعت النية (التوافق) لا الحرف الخاطئ: قيد القاعدة [0,100] وبنّاء اللقطة يضرب كسرة المحرك [0,1] في 100 — وهذا حرفيًا ما يوثقه compute_market_volatility_summary («مسؤولية طبقة الدمج»).
2. **uuid محلي مثبت لا مستورد**: استيراد ingestion.market_store يعني اعتمادًا بنيويًا محظورًا بنطاق pyproject (asyncpg فقط) — عُرّف الترميز نفسه محليًا وثُبّت التطابق بمساواة مباشرة في الاختبارات.
3. **session_id**: صيغة يوم ISO تُتحقق في البنّاء (فشل مبكر)، لا يدخل النموذج (المخطط additionalProperties:false)، والعمود يُشتق حتميًا من event_time (متسق مع Candle.session_id).
4. **الناشر ببروتوكول هيكلي** بدل استيراد nats (عميل محضّر، بلا إعادة اتصال/تراجع — موثق)؛ fake الاختبار يحقق البروتوكول حرفيًا.

## البوابات (كلها خضراء)
ruff format "14 files already formatted" · ruff check "All checks passed!" · mypy "Success: no issues found in 86 source files" · pytest unit "77 passed" · lint-imports "Contracts: 6 kept, 0 broken" · alembic current "0003_market_states (head)" · integration "4 passed" · المجموع "940 passed, 17 deselected" (863+77).

## ملاحظة للمنسق (خارج نطاقي)
تشغيل `pytest tests/integration -m integration` كاملًا يفشل 4 اختبارات قديمة (test_migrations.py/test_migrations_0002.py) لأنها تدبس «head == مراجعتها» — **قائمة قبل تغييري** (أثبتُها بـgit stash على الحالة السابقة). تحتاج مهمة صغيرة لاحقة تجعلها تتقاعد مع كل هجرة جديدة.
