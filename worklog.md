---
Task ID: 0
Agent: Main Agent (Z.ai Code — Architect/Owner)
Task: استلام Master Plan.md وتنفيذ المراحل الأربع (فهم عميق ← تحليل نقدي ← خطة تنفيذ ← انتظار إشارة البدء)

Work Log:
- فحص `/home/z/my-project/upload/` — المجلد فارغ تمامًا؛ الملف المرفق المُعلن `Master Plan.md` لم يصل إلى نظام الملفات.
- بحث شامل: `**/*Master*` عبر `/home/z`، بحث عن أي `.md` حديث خارج `node_modules`، فحص git log/stash — لا أثر للملف في أي مكان أو أي جلسة سابقة (سجل git = Initial commit فقط).
- تدقيق بيئة تنفيذ كامل: لا Docker، لا Postgres/Redis/NATS مثبتة، الشبكة متاحة (npm registry 200, github 200)، Node 24.21 + Bun 1.3.14 + Python 3.12 متاحة، 4.1GB RAM / 2 cores، منفذ خارجي واحد عبر Caddy مع `?XTransformPort=`.
- قرار ADR-001: رفض اختلاق تحليل لمستند لم يُقرأ. إنشاء `docs/architecture/session_record.md` موثقًا العائق والدليل والقرار ونتائج تدقيق البيئة.

Stage Summary:
- **عائق حقيقي مُعلن:** Master Plan.md لم يصل. المراحل 1–4 كلها معلقة عليه.
- **أُنجز فعليًا:** تدقيق بيئة كامل سيُغذي plan_review.md لاحقًا (لا Docker، NATS قابل للتثبيت كثنائية مستقلة، قيود الموارد والبوابة موثقة).
- **الأثر على الوكلاء اللاحقين:** لا يُكتب أي كود أو خطة قبل وصول نص الخطة الفعلي وإشارة البدء الصريحة من المستخدم. سجل القرارات يبدأ من `docs/architecture/session_record.md`.

---
Task ID: 0-b
Agent: Main Agent (Z.ai Code — Architect/Owner)
Task: ضبط مجلدات الرفع والاستقبال لتكون قابلة للقراءة والكتابة، بحيث أي ملف يُرفع يصل ويبقى ظاهرًا.

Work Log:
- فحص الصلاحيات: `upload/` كان 777 أصلًا (root-owned) — الخطر الحقيقي فقدان الملفات لا الصلاحيات. `download/` رُفع إلى 777.
- أنشئ `received/` (صندوق استقبال دائم 777).
- اكتشاف بيئي حاسم (اختبار محكم بنمطين): العمليات الخلفية التي يطلقها الوكيل تُقتل بين أوامر الأدوات حتى مع nohup/setsid؛ نمط **double-fork** فقط ينجو. عمليات المنصة (خادم dev) وحدها مضمونة البقاء.
- بُني مراقب دائم داخل خادم dev: `src/instrumentation.ts` (دخيل رفيع) + `src/lib/upload-watcher.ts` (تنفيذ: استطلاع upload/ كل ثانية، ثبات الحجم عبر استطلاعين، نسخ فوري إلى received/، سجل .arrival-log، حرس حالة-واحدة globalThis+pidfile).
- اكتشاف وتصحيح خطأ معماري: الاستيرادات الساكنة لـ node:* في instrumentation تُفسد بناء edge → النمط الرسمي: استيراد ديناميكي داخل حرس NEXT_RUNTIME==="nodejs".
- تفعيل عبر إعادة إقلاع نظيفة (تعديل next.config.ts + إصلاح allowedDevOrigins بـ *.space-z.ai).
- اختبارات نهاية-إلى-نهاية نجحت: ملف بمسافة بالاسم ومحتوى عربي → لقطة في received/ خلال ~2s مع سطر SNAPSHOT موثق؛ حذف الأصل لا يمس اللقطة؛ lint نظيف؛ الخادم 200.
- نسخة bash احتياطية في `.zscripts/upload-watcher.sh` (تشغيل يدوي فقط — انتبه: لا تُطلق إلا بنمط double-fork).

Stage Summary:
- **طبقة استلام ملفات دائمة جاهزة ومختبرة:** أي ملف يصل `upload/` يُؤمَّن في `received/` خلال ثانيتين حتى لو نُظّف المجلد الأصلي.
- **معرفة بيئية موثقة في session_record.md (ADR-002):** أنماط إطلاق العمليات الدائمة، نمط instrumentation الإلزامي، رافعة إعادة الإقلاع عبر next.config.ts — كلها ستُبنى عليها خطة التنفيذ.
- **بانتظار:** إعادة إرسال Master Plan.md أو لصقه — فور وصوله تبدأ المرحلة 1 (الفهم العميق).

---
Task ID: 0-c
Agent: Main Agent (Z.ai Code — Architect/Owner)
Task: تجعل مجلد الرفع مرئيًا في متصفح ملفات المستخدم بعد اكتشاف أن invisibility هي المشكلة.

Work Log:
- تحقق من نظرية المستخدم: upload/ غير مرئي له → الفحص كشف أنه نقطة تثبيت fuse.ossfs (سحابة OSS) بملكية root فوق tmpfs، لا تُنقل (Device or resource busy)، ومستبعدة صراحة من خريطة اللقطات (95 مدخلًا ولا ذكر لـ upload) — الإخفاء بالتصميم، غير قابل للإصلاح من الداخل.
- القرار ADR-004: بديل محلي كامل الأهلية — أنشئ inbox/ (z-owned, 777, فيه README عربي شارح) يتبع مسار الظهور نفسه (docs/ وreceived/ تظهران فعلًا في متصفحه).
- رقّي المراقب إلى v2 (src/lib/upload-watcher.ts): مصادر متعددة [upload/, inbox/] بدل مصدر واحد؛ أعد الإقلاع عبر رافعة next.config.ts → pid 2338 "watching: upload, inbox".
- اختبار نهاية-إلى-نهاية لـ inbox: ملف بمسافة بالاسم → لقطة في received/ خلال ~2s مع سطر SNAPSHOT موثق. تنظيف المخلفات. lint نظيف. الخادم 200.
- ملاحظة مزامنة: مرآة /tmp/my-project تلتقط على حدود الرسائل (docs/received فيها من مزامنة 03:39؛ inbox ستظهر في المزامنة التالية).

Stage Summary:
- **inbox/ جاهز كوجهة استقبال مرئية للمستخدم**، والمراقب v2 يغطي upload/ + inbox/ معًا بأخذ لقطات فورية إلى received/.
- **لغز upload/ محسوم معماريًا**: تثبيت سحابي للمنصة، مستبعد من اللقطات بالتصميم، وقناة البوابة إليه معطولة سحابيًا.
- **بانتظار**: وصول Master Plan.md (لصقًا نصًا — المسار المضمون — أو في inbox/ إن كان متصفح المستخدم يدعم الرفع) لبدء المرحلة 1 فورًا.

---
Task ID: 1 (Phases 1-3 of session protocol)
Agent: Main Agent (Z.ai Code — Architect/Owner)
Task: استلام Master Plan.md من GitHub (قرار المالك)، ثم تنفيذ المراحل 1-3: الفهم العميق، التحليل النقدي، خطة التنفيذ.

Work Log:
- استلام المصدر: استنساخ https://github.com/Moh503-qtb/trade.git → الملف الوحيد: Master Plan.md (88,103 bytes، 3,270 سطرًا). التقطه المراقب إلى received/ بسجل موثق (04:01:13) + نسخة قانونية في docs/Master Plan.md. (تنبيه مُوثق: توكن GitHub شاركه المالك في المحادثة — يوصى بإبطاله وتدويره فور انتهاء الحاجة.)
- المرحلة 1 (فهم عميق): قراءة كاملة 3,270 سطرًا على 8 دفعات منهجية — سلسلة السببية، الطبقات الست، هرمية الأسبقية §50، محرك الدليل §19، قاموس الأحداث §20، دورة السيناريو §18، لا-تداول §22، مخاطرة §23، تعلم §29، برنامج التحقق A-G §39، معايير القبول §40، ترتيب البناء §46، MVP §51، DoD Appendix B.
- المرحلة 2: كتابة docs/architecture/plan_review.md — 10 نقاط قوة متبناة، 11 فجوة حقيقية (G-01..G-11) بأهمها بيئة التنفيذ الغائبة من الخطة ومصدر البيانات غير المسمى، 6 التباسات (A-01..A-06) بحلولها، 15 قرارًا هندسيًا (D-01..D-15) ببدائلها المرفوضة، ترتيب التنفيذ الفعلي، 9 مخاطر بناء بتخفيفاتها، معايير نجاح ميكانيكية.
- المرحلة 3: كتابة docs/architecture/build_plan.md — استراتيجية التشغيل المزدوج (Compose قانوني + supervisor محلي: embedded-PG/NATS/MinIO user-space)، بنية المستودع الفعلية كاملة، جدول حزم بإصدارات، المراحل 0→10 مهامًا بمدخلات/مخرجات/بوابات تحقق/اختبارات + خارطة ما بعد MVP، استراتيجيات الاختبار الست، Git/النسخ، قائمة المؤجل صراحة، بروتوكول التقدم.

Stage Summary:
- **الوثائق المعمارية الثلاث اكتملت:** plan_review.md + build_plan.md + المصدر Master Plan.md، والحالة الآن: **بانتظار إشارة البدء الصريحة من المالك قبل كتابة أي سطر كود** (بروتوكول الجلسة — المرحلة 4).
- **قرارات مفصلية جاهزة للتنفيذ:** D-01 تشغيل مزدوج، D-02 Binance USDⓈ-M كمصدر مرجعي (aggTrades → footprint صادق)، D-03 رياضيات الدمج المكتملة، D-12 طوبولوجيا منطقية/تشغيل مجمّع بفرض import-linter، D-15 تغليف mini-services لإدارة المنصة.
- **نطاق الالتزام:** MVP = المراحل 0→10 ببوابة §51، وما بعده خارطة معلنة.

---
Task ID: 0.8
Agent: compose-spec-builder (full-stack-developer)
Task: مواصفة docker-compose للخادم الهدف + Dockerfiles + سكربت تحقق بنيوي

Work Log:
- قراءة السياق الكامل: worklog.md (المهام 0–1) + build_plan.md (A.1 الطوبولوجيا · A.3 المنافذ · A.4 الأسرار · C الأدوات) + plan_review.md (D-01 التشغيل المزدوج · D-10 Alembic · G-01 بيئة التنفيذ)، وفحص شجرة engine/ الفعلية (18 حزمة workspace، apps/api بـengine_api.main:app على /healthz، .env.example، Makefile).
- اختبار تجريبي حاسم في /tmp (محاكاة مرحلة deps بالضبط): «uv sync --frozen --all-packages --no-dev» مع pyproject+lock فقط (بلا src) يخرج 0 **لكن دون كتابة ملفات .pth** — تركيب workspace القابل للتحرير يتطلب المصدر حاضرًا وقت التركيب، وإلا دارات الحاوية بلا مسارات استيراد (فشل صامت). الحل المعتمد: مرحلتان — deps بـ«--no-install-workspace» (الطبقة الغالية القابلة للتخزين) ثم sync كامل بعد نسخ الشيفرة؛ مثبت بمحاكاة كاملة: 19 pth + «import engine_api, engine_worker, engine_replay» تعمل.
- اكتشاف أن alembic في مجموعة dev فقط (غير مثبت مع --no-dev): يُثبَّت بالإصدار المقفول نفسه من uv.lock (1.20.0) بعد sync النهائي (كيلا يقصّه exact-sync) — موثق في Dockerfile مع شرط حذفه عند نقله لتبعيات تشغيل.
- كتابة infra/docker-compose.yml: الخدمات الثماني (postgres/nats/minio/storage-init/migrate/engine-worker/engine-api/engine-replay) بأوصاف عربية موجزة فوق كل خدمة، healthchecks حقيقية (pg_isready · wget /healthz · mc ready + احتياط curl على /minio/health/live · healthcheck.py للـapi)، depends_on بشرط service_healthy/service_completed_successfully، JetStream (-js -sd /data -m 8222)، expose داخلي فقط (لا ports لأي بنية تحتية)، نشر وحيد 127.0.0.1:4001:4001 لـengine-api، شبكة bridge مسماة engine-internal، volumes مسماة ثلاث، env_file «../.env» بصيغة required:false (يصمد غيابه) مع ${VAR:-default} لكل المتغيرات، وإعادة تعيين صريحة للمتغيرات الحرجة بأسماء الخدمات (ENGINE_DATABASE_URL→postgres:5543 · NATS_URL→nats:4222 · S3_ENDPOINT→minio:9100 — قيم .env الشكل-sandbox لا تصل للحاويات)، postgres يستمع داخليًا على 5543 بإعدادات محافظة (shared_buffers=128MB · max_connections=25)، سجلات دوارة json-file 10m×3، وprofile=replay لا يقلع افتراضيًا.
- كتابة infra/dockerfiles/Dockerfile.engine: multi-stage من ghcr.io/astral-sh/uv:python3.12-bookworm-slim — مرحلة deps تنسخ pyproject+lock+ملفات تعريف الحزم الـ18 فقط ثم sync بلا workspace؛ مرحلة runtime تنسخ الشجرة (شيفرة حقيقية فوق مسارات التحرير) + venv الجاهز + sync كامل + تثبيت alembic المقفول، مستخدم غير جذري engine، حرس أمني آلي «test ! -e /app/.env» يفشل البناء لو تسرب .env لأي طبقة (§37.1)، ARG SERVICE (api/worker/replay/migrate) يقود entrypoint.sh، وCOPY alembic.ini مقصود fail-fast قبيل المهمة 0.6.
- كتابة infra/dockerfiles/entrypoint.sh (تفريع حسب SERVICE: uvicorn engine_api.main:app على 0.0.0.0 داخل الحاوية · python -m engine_worker · python -m engine_replay · alembic upgrade head · exec "$@" عائدًا) وhealthcheck.py (stdlib خالص — http.client يضرب /healthz؛ الصورة slim بلا curl/wget).
- كتابة scripts/validate-compose.py: 16 فحصًا آليًا (بنية YAML، اكتمال الخدمات الثماني، فحوص صحة البنية التحتية، loopback فقط للنشر، شروط اعتماد worker وapi، JetStream في أمر nats، volumes مسماة، profile الـreplay، env_file اختياري ../.env، إشارة قاعدة البيانات لاسم الخدمة لا localhost، إعدادات postgres المحافظة، دلالات one-shot، فحص صحة api، استمرارية worker، شبكة الجميع) — أي فشل: رسالة عربية + خروج 1؛ نجاح كامل: قائمة الفحوص + جدول ملخص.
- كتابة infra/README.md: الغرض (D-01)، جدول الفروق عن وضع sandbox/supervisor، أوامر التشغيل القانونية على الهدف (up -d مع --env-file .env وسببها: الاستيفاء مقابل env_file، migrate، logs، replay بـprofile، down)، جدول متغيرات البيئة، شرح إعادة التعيين بأسماء الخدمات، ووصول لوحة Next (loopback مباشر / بروكسي عكسي / XTransformPort=4001)، والقيود الموثقة.
- فحوص نهائية: فك YAML ناجح مع تحقق قيمي لكل أمر/منفذ حرج، sh -n للمدخل، اختبار سلوك healthcheck.py فعليًا (منفذ مغلق→1، خادم وهمي 200 على 4001→0)، بقاء مجلد migrations الفارغ في سياق tar للبناء، وruff (format+check) نظيف على الملفين البايثونيين الجديدين. ملاحظة: مخالفات ruff الموجودة في packages/schemas وtests/ من مهمة موازية (0.3) لم تُمَس التزامًا بقيد المسارات.

Stage Summary:
- **المواصفة القانونية جاهزة:** 8 خدمات — postgres (16-alpine، داخلي 5543، إعدادات محافظة) · nats (2.10-alpine، JetStream+volume) · minio (9100/9101 داخلي) · storage-init (one-shot: حزمة engine-raw عبر mc، restart:no) · migrate (one-shot: alembic upgrade head ينتظر postgres healthy) · engine-worker (unless-stopped، ينتظر صحة الثلاث + اكتمال migrate وstorage-init) · engine-api (النشر الخارجي الوحيد: 127.0.0.1:4001:4001، فحص /healthz) · engine-replay (profile مستقل لا يقلع افتراضيًا) — على شبكة engine-internal وvolumes مسماة.
- **التحقق البنيوي: نجاح 16/16، خروج 0** عبر «cd engine && unset VIRTUAL_ENV && uv run --no-sync python scripts/validate-compose.py» (لا Docker في الـsandbox — البناء الفعلي على الخادم الهدف؛ بوابة 0.8 «docker compose config» تُستوفى هناك).
- **قيود موثقة:** alembic.ini يصل مع 0.6 (COPY مقصود fail-fast) · alembic مثبت بالإصدار المقفول من مجموعة dev · يوصى عند النشر الفعلي بإنشاء engine/.dockerignore وتثبيت digests (خارج نطاق المهمة — قيد المسارات) · minio/minio وminio/mc بوسم latest مع توثيق مرآة quay.io وتوصية التثبيت · تتطلب الصيغة Compose v2.24+ (env_file.required).

---
Task ID: 0.3
Agent: schemas-builder (full-stack-developer)
Task: بناء حزمة schemas الكاملة + تصدير JSON Schema + اختبارات

Work Log:
- قراءة المصدر الأعلى بدقة قبل أي كود: worklog + build_plan (§A.5) + plan_review (D-03/D-07/A-03) + أقسام Master Plan المطلوبة (§7.1/7.4، §8.1/8.2، §9.2-9.4، §10.2-10.5، §12.1-12.7، §13.1، §18.1/18.2/18.5، §19.1-19.4، §20 كاملًا، §22.1، §23.1-23.4، §24.1/24.2/24.4/24.5، §27.1، §29.1، §31، §32، §2.6).
- enums.py: 12 تعدادة StrEnum بقيم UPPERCASE حرفية — DataQuality (9 §7.4) · SignalState (4 §27.1) · Direction (3) · HTFBias (5 §9.2) · MarketRegime (8 §9.3) · SessionType (5 وفق A-03 إذ §9.4 بلا قيم حرفية) · EvidenceGroup (6 §19.3) · EventType (45 = قاموس §20 كاملًا بترتيبه) · ScenarioState (12 §18.2) · OrderPolicy (5 §24.2) · SweepClassification (5 §10.4) · HardBlockReason (15 §22.1 بنصه الإنجليزي تعليقًا) + ثابتان رقميان منقولان حرفيًا: DEFAULT_GROUP_SHARES (§19.3: 25/20/30/10/10/5) وDEFAULT_EVENT_WEIGHTS (عمود Weight في §20؛ None للأربعة الحاجبة صلبًا).
- _types.py: أنواع مشروطة مشتركة خاصة بالحزمة — UTCDatetime (يرفض الساذج ويطبّع الواعي إلى UTC §7.1)، UnitInterval، SignedUnit، Price/PositiveFloat، NonNegativeFloat، FiniteFloat، Percentile، NonNegativeInt.
- 15 نموذجًا مجمّدًا (frozen + extra="forbid"): EventEnvelope (الحقول التسعة §32 حرفيًا، event_id UUID) · TradeEvent (§7.1 كاملًا + price/quantity/buyer_is_maker لعدوانية aggTrades) · Candle (§8.1 كاملًا + مفاتيح جدول candles §31.2 + is_closed لفصل المتطور عن المؤكد §27) · FootprintBar (§8.2 كاملًا + source_feed/methodology إلزاميان §12.7) · MarketStateSnapshot (مثال §32 حرفيًا) · EvidenceRecord (§19.1 بحدوده: direction_score ∈ [-1,1]، أربعة حقول ∈ [0,1]، prior_weight/context_modifier بلا حد كالنص، correlation_group_id §19.4) · TriggerDefinition (condition_type+params) · InvalidationRule (structural_level+volatility_buffer+accept_through §18.5/§23.4) · TargetZone (§10.5) · PriceZone (تمثيل entry_zone المشترك §18.1/§24.1) · Scenario (§18.1 كاملًا؛ scenario_score ∈ [0,1] درجة خام لا احتمال §2.6؛ calibrated_probability اختياري §19.6) · OrderIntent (§24.1 كاملًا) · SlippageRecord (§24.4 الستة) · LatencyRecord (§24.5 الستة) · ExperienceRecord (§29.1 الـ17 حرفيًا؛ mfe/mae صغيرتين كسابقة poc/vah/val في §8.2).
- export.py: ALL_MODELS (15 مرتبة) + أمرا write/check — write يولد generated/ حتميًا 100% (json.dumps بـindent=2 وsort_keys وسطر نهائي) + index.json (‏{model: file, schema_version}) + README.md جدول عربي؛ check يعيد التوليد في الذاكرة ويقارن بايت-بايت ويرفض المجلد الفارغ/المفقود والملفات الزائدة/المنحرفة برسالة واضحة + exit 1.
- __init__.py: إعادة تصدير كاملة بـ__all__ صريح (31 اسمًا) مع بقاء SCHEMA_VERSION و__version__.
- الاختبارات: test_schemas_enums.py (45 — القيم منسوخة من نص الخطة كثوابت مرجعية مستقلة) · test_schemas_models.py (91 — round-trip JSON لكل نموذج + رفض خارج الحدود + جمود + منع الحقول الغريبة + عقد الوقت) · test_schemas_export.py (12 — توليد/تحقق/idempotence/عبث ثم استرجاع/مجلد فارغ عبر tmp_path معزول) · test_schemas_property bounds (16 — hypothesis داخل الحدود يبني وخارجها يُرفض).
- توليد generated/ (15 مخططًا + index.json + README.md) وتحويل make schemas أخضر؛ رفع كل مخالفات ruff (ترتيب استيرادات، UP017 datetime.UTC، RUF022 ترتيب __all__، RUF043 raw match، E501) وإخضاع كل شيء للبوابة.

Stage Summary:
- **15 نموذج Pydantic v2 + 12 تعدادة + ثابتان رقميان منقولان حرفيًا من الخطة؛ 164 اختبارًا جديدًا (المجموع 186).**
- **make gate خضراء بالكامل:** ruff format --check (43 ملفًا) ✓ · ruff check ✓ · mypy strict (38 ملفًا) ✓ · import-linter (6 عقود، schemas pure leaf) ✓ · pytest 186 passed.
- **إضافات موثقة لا انحرافات:** PriceZone (نوع entry_zone الذي لم تعرفه الخطة) وDEFAULT_EVENT_WEIGHTS (نقل حرفي لعمود Weight §20 تحت قاعدة «الثوابت الرقمية تُنقل حرفيًا») وSessionType وفق A-03. حقول ExperienceRecord غير المنمذجة بعد (risk/execution/fills/positions) JSONB موثقة إلى حين مرحلتي المخاطرة والتنفيذ.
