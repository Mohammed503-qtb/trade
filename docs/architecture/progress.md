# جدول التقدم — مراحل × مهام × تحقق

> بروتوكول §H من build_plan: لا انتقال لمرحلة تالية قبل تحقق آلي موثق
> لبوابة الحالية. كل صف: الأمر الفعلي الذي أثبت الإتمام.

## المرحلة 0 — الأساس والمستودع والتشغيل

| المهمة | الحالة | التحقق | تاريخ | دليل |
|---|---|---|---|---|
| 0.1 هيكل المستودع | ✅ | make doctor | 2026-09-27 | شجرة engine/ الكاملة + uv workspace (18 حزمة) |
| 0.2 عقود الحدود | ✅ | lint-imports ضمن make gate | 2026-09-27 | 6 عقود import-linter، 0 مكسور |
| 0.3 حزمة schemas | ✅ | make schemas (idempotent) + اختبارات | 2026-09-27 | 15 نموذج + 12 تعدادة + 164 اختباراً جديداً (186 كلياً) + generated/ ملتزم |
| 0.4 الطوبولوجيا التحتية | ✅ | supervisor health | 2026-09-27 | nats 2.10.24 + PG 16.4 (Zonky) + seaweedfs عبر provision.sh — ADR-005/006 + تئام قاعدة البيانات ADR-008 |
| 0.5 supervisor + mini-services | ✅ | إقلاع من الصفر + بقاء الخدمات | 2026-09-27 | services.yaml (5 خدمات متدرجة) + غلافا D-15: engine-infra (يدير supervisor) وengine-api (ADR-007) — بقاء مثبت عبر إعادة إقلاع supervisor من الغلاف |
| 0.6 الهجرة الأولى | ✅ | alembic upgrade head + اختبار صعود/هبوط | 2026-09-27 | 0001_reference_tables (instruments/feeds/strategies §31.1) — 3 اختبارات integration خضراء + migrate oneshot يشتغل عند كل إقلاع |
| 0.7 بوابة الجودة | ✅ | make gate | 2026-09-27 | ruff + mypy strict + import-linter + pytest كلها خضراء |
| 0.8 compose الهدف | ✅ | validate-compose.py 16/16 | 2026-09-27 | 8 خدمات + Dockerfile.engine + entrypoint + healthcheck — البناء الفعلي عند توفر Docker على الهدف |
| 0.9 التوثيق الحي | ✅ | مراجعة | 2026-09-27 | decisions.md (ADR-001..012) + progress.md (هذا الملف) — تُنسخ إلى engine/docs |

**بوابة الخروج 0:** `make doctor && make gate && supervisor health` —
كلها خضراء (انظر أوامر الإثبات أدناه) + لا أسرار في git (فحص git log -p
للمسارات الحساسة نظيف؛ .env متجاهل).

## المرحلة 1 — الابتلاع القانوني (مكتملة 2026-09-27)

| المهمة | الحالة | التحقق | تاريخ | دليل |
|---|---|---|---|---|
| 1.1 محول Binance | ✅ | عينة حية تُلتقط وتُطابق | 2026-09-27 | binance.py: parse_aggtrade/WS + REST بترقيم زمني — اختبار حي ضد fapi.binance.com |
| 1.2 التنقيح والطابع الزمني | ✅ | fixtures مكرر/معكوس/فجوة | 2026-09-27 | refine.py بترتيب §33.1 الحرفي — اختبارات التصنيف الثلاثة خضراء |
| 1.3 حالات الجودة التسع | ✅ | حقن حالات ⇒ تصنيف صحيح | 2026-09-27 | quality.py: QualityTracker + سلّم شدة + is_decision_eligible §7.4 |
| 1.4 منشئ الشموع | ✅ | مطابقة golden 100% | 2026-09-27 | candles.py حدثي §27 + إطار صريح tick→1m — 47 اختباراً |
| 1.5 المخزن الخام | ✅ | جولة كتابة/قراءة + ميتاداتا | 2026-09-27 | raw_store.py Parquet/S3 حتمي البايتات + هجرة 0002 |
| 1.6 اختبارات الجودة الشاملة | ✅ | make verify-phase1 | 2026-09-27 | العينة المرجعية 3999 صفقة + الذهبية 9/9 + market_store idempotent |

**بوابة الخروج 1 (مغلقة):** `make verify-phase1` — الحتمية (نفس الهاش عبر المسار الأرشيفي والإعادة من الخام) + الذهبية (شموع aggTrades تطابق klines البورصة 9/9 دلاء مكتملة 100%) + الخلود (round-trip المخزن الكائني) + القاعدة (3999 حدث idempotent + 10 شموع hash موحد). اختبارات فجوة/تكرار خضراء ضمن الـ363.

## المراحل 2–10

لم تبدأ. التفاصيل في build_plan.md §D.

---

## أوامر إثبات بوابة المرحلة 0 (منذ 2026-09-27)

```bash
cd engine
unset VIRTUAL_ENV
make doctor                        # بيئة + تبعيات + إصدارات ✓
make gate                          # ruff + mypy strict + lint-imports + pytest (186 passed) ✓
uv run --no-sync python infra/local/supervisor.py health
# postgres ✓ · nats ✓ · seaweedfs ✓ · migrate ✓ (EXITED_OK) · worker ✓ — سليم (exit 0)
curl -s http://127.0.0.1:4001/healthz   # {"status":"ok",...,"schema_version":"1.0.0"}
uv run --no-sync pytest -m integration -q   # 3 passed (هجر alembic صعود/هبوط/إعادة)
```

## سجل الجلسات

| التاريخ | الجلسة | الخلاصة |
|---|---|---|
| 2026-09-27 | التدقيق والاستلام | 0-a/0-b/0-c/1: تدقيق بيئة + طبقة استلام + استلام الخطة من GitHub + المراحل 1–3 من بروتوكول الجلسة (فهم/تحليل/خطة) |
| 2026-09-27 | بناء المرحلة 0 | 0.8 compose · 0.3 schemas · 0.1+0.2 هيكل وعقود · 0.4/0.5 بنية تحتية وsupervisor وأغلفة · 0.6 alembic · 0.7 بوابة · 0.9 توثيق — **بوابة 0 مغلقة** |
| 2026-09-27 | بناء المرحلة 1 | 1.1+1.2+1.3 محول وتنقيح وجودة · 1.4 شموع · 1.5 مخزن خام + هجرة 0002 · 1.6 عينة مرجعية + verify-phase1 — **بوابة 1 مغلقة**: ذهبية 100% وحتمية hash-for-hash |
