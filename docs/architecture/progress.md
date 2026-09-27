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

## المرحلة 1 — الابتلاع القانوني (قيد التنفيذ)

| المهمة | الحالة | التحقق |
|---|---|---|
| 1.1 محول Binance | ⬜ | عينة حية/تاريخية تُلتقط وتُطابق مجموع تحقق |
| 1.2 التنقيح والطابع الزمني | ⬜ | fixtures مكرر/معكوس/فجوة تُصنف صحيحاً |
| 1.3 حالات الجودة التسع | ⬜ | حقن حالات ⇒ تصنيف صحيح + بث NATS موسم |
| 1.4 منشئ الشموع | ⬜ | إعادة بناء من خام 1m مطابقة golden 100% |
| 1.5 المخزن الخام | ⬜ | جولة كتابة/قراءة Parquet في S3 + ميتاداتا PG |
| 1.6 اختبارات الجودة الشاملة | ⬜ | make verify-phase1 |

**بوابة الخروج 1:** إعادة تُنتج الشموع من الخام بتّية 100%؛ اختبارات فجوة/تكرار خضراء؛ الخام خالد في S3.

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
