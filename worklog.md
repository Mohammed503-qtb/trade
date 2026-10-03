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

---
Task ID: 0.6
Agent: alembic-builder (full-stack-developer)
Task: الهجرة الأولى عبر Alembic — إعداد env غير متزامن (asyncpg) + الجداول المرجعية الثلاثة (§31.1) + اختبارات صعود/هبوط/إعادة صعود

Work Log:
- قراءة السياق الكامل قبل أي كود: worklog (المهام 0→0.8) + build_plan §D مهمة 0.6 + Master Plan §31.1 (السطور 1921-1957) + services.yaml (migrate: oneshot، skip_if_missing=alembic.ini، cwd={engine}) + common/config.py + pyproject.toml، وفحص الواقع: postgres 16.4 حي على 5543 بقاعدة engine فارغة، alembic 1.20.0 وasyncpg 0.31.0 في venv.
- اكتشاف عائق صلب بالتجربة: قالب env غير المتزامن يستورد sqlalchemy.ext.asyncio الذي يفشل بلا greenlet (غير مثبت — alembic يجلب sqlalchemy بلا extra [asyncio]). عولج بـ `uv add --dev "sqlalchemy[asyncio]>=2.0"` → أُضيف greenlet 3.5.6 فقط (فرق uv.lock نظيف: +74 سطرًا، لا مساس بأي إصدار آخر).
- اكتشافان حاسمان بالتجربة المباشرة قبل كتابة env.py: (أ) create_async_engine يرفض `postgresql://` المجردة (يتوقع psycopg) → وجبت إعادة كتابة الدرايفر صراحةً إلى postgresql+asyncpg؛ (ب) str(URL) في SQLAlchemy يستبدل كلمة المرور بـ *** → كان سيكسر الاتصال بصمت؛ الحل: render_as_string(hide_password=False) — موثق بتعليق في env.py.
- كتابة engine/alembic.ini: الحد الأدنى القانوني — [alembic] script_location=migrations + أقسام تسجيل سجلات قياسية؛ خيار sqlalchemy.url معلّق بتعليق عربي يشرح أنه يُضبط برمجيًا في env.py (§37.1 لا أسرار).
- كتابة engine/migrations/env.py: القالب غير المتزامن الكامل (asyncio.run + async_engine_from_config + NullPool)؛ الرابط من common.config.load_settings() مع أولوية قصوى لتمريرة `-x sqlalchemy.url=`؛ وضعا offline وonline كلاهما مختبر ويعمل؛ compare_type=True + compare_server_default=True (عمق مقارنة لـautogenerate لاحقًا)؛ target_metadata = MetaData بخريطة تسمية pk/uq/ck/fk/ix لأسماء قيود حتمية.
- كتابة engine/migrations/script.py.mako: القالب القياسي بترويسة عربية تفرض اصطلاح معرف المراجعة NNNN_وصف_إنجليزي وتوثّق وثاقة §31 وشرط ADR لأي انحراف.
- كتابة engine/migrations/versions/0001_reference_tables.py (rev=0001_reference_tables، down_revision=None): instruments (UUID PK، symbol فريد، CheckConstraint لإيجابية tick_size وlot_size، contract_multiplier افتراضي 1، status افتراضي ACTIVE، created/updated timestamptz بـnow()) + فهرس فريد ux_instruments_venue_symbol؛ feeds (timezone افتراضي UTC، latency_profile قابل للإلغاء، methodology_version إلزامي §12.7) + فهرس فريد ux_feeds_provider_venue_data_type؛ strategies (name فريد، active افتراضي false — لا تفعيل إلا بقرار). UUID عبر sa.Uuid() والطوابع عبر postgresql.TIMESTAMP(timezone=True).
- تصحيح تجريبي لأسماء القيود: قالب ck_%(table_name)s_%(constraint_name)s في خريطة التسمية (يسقطه alembic على op.create_table) ضاعف البادئة (ck_instruments_ck_instruments_…) → أعيدت الأسماء في الهجرة مجردة البادئة (tick_size_positive/lot_size_positive) فتكتمل عند التنفيذ إلى ck_instruments_tick_size_positive — تحقق مباشر من pg_constraint.
- كتابة engine/tests/integration/test_migrations.py (علامة integration): صعود يتحقق من أعمدة الجداول الثلاثة كاملة (اسم/نوع/is_nullable عبر information_schema) + الافتراضات + الفهرسين الفريدين (pg_indexes) + قيدي الإيجابية (pg_constraint) + alembic_version؛ هبوط يتحقق من زوال الجداول (مع تصحيح التوقع: alembic_version يبقى كجدول إدارة لكن يجب أن يخلو من الرؤوس — سلوك alembic المثبت)؛ إعادة صعود بعد هبوط كامل مع تكرار upgrade head (idempotence عبر version_num). الاختبارات تشغّل الواجهة الفعلية نفسها ([sys.executable, -m alembic] من جذر engine — حرفيًا كما في services.yaml) عبر subprocess، وfixture جلسة asyncpg مباشرة، وعقد نهائي: fixture تلقائي (module autouse) يترك القاعدة عند upgrade head أيًا كانت النتائج.
- تعديل pyproject [tool.pytest.ini_options]: addopts أصبح `--strict-markers -q -m 'not integration'` كي لا يشغل pytest الافتراضي اختبارات البنية الحية (تحقق مزدوج: من كود pytest أن addopts يُفصل بـ shlex posix فالاقتباس يعمل، ثم عمليًا: 186 passed + 3 deselected)؛ خيار -m اللاحق في سطر الأوامر يتجاوز addopts (سلوك الأخير-يفوز) فـ`make test-integration` يعمل.
- التحقق النهائي (كل الأوامر بـ unset VIRTUAL_ENV من جذر engine): ruff format --check وruff check على نطاق المهمة (migrations + tests) = نجاح كامل؛ mypy = Success بلا ملاحظات في 39 ملفًا؛ lint-imports = 6 عقود محفوظة 0 مكسورة؛ pytest الافتراضي = 186 passed + 3 deselected في 2.14s؛ pytest -m integration -q = 3 passed؛ alembic upgrade head نجح وalembic current = `0001_reference_tables (head)`؛ القاعدة تُركت عند head بجداولها الأربعة (الثلاثة + alembic_version)؛ فحص supervisor health: postgres/nats/seaweedfs/worker كلها ✓ وmigrate ✗ SKIPPED — متوقع حرفيًا كما نصت المهمة: الجلسة الحالية أقلعت قبل وجود alembic.ini فحالة oneshot المجمدة SKIPPED؛ أثبتنا عمليًا أن الأمر نفسه (python -m alembic upgrade head من جذر engine) ينجح فسيعمل عند إقلاع supervisor القادم.
- عائق موجود مسبقًا خارج نطاقي (موثق لا مُصلح — القيد الصريح "لا تلمس supervisor.py"): ruff كامل المستودع يفشل على engine/infra/local/supervisor.py وحده (15 خطأ + تنسيق في نسخة العمل، و13 خطأ + تنسيق حتى في نسخة HEAD الملتزمة — أثبتُ بتمرير git show عبر ruff). كل ملفات هذه المهمة نظيفة 100%، والفشل المتبقي ليس من صنعها.
- فحص أسرار على ملفات الالتزام: نظيف — لا URL ولا كلمة مرور فعلية (المطابقات الوحيدة أمثلة توثيقية postgresql://...).
- commit afedc3a بالرسالة المقررة `feat(engine): المهمة 0.6 — Alembic + الهجرة الأولى للجداول المرجعية (§31.1)` — 7 ملفات (alembic.ini، migrations/env.py، migrations/script.py.mako، migrations/versions/0001_reference_tables.py، tests/integration/test_migrations.py، pyproject.toml، uv.lock). ملف supervisor.py (تعديل WIP غير ملتزم لوكيل آخر) لم يُمَس ولم يُلتزم.

Stage Summary:
- **المنتجات:** ركيزة الهجرة كاملة العدة — alembic.ini نظيف من الأسرار + env.py غير متزامن (asyncpg من الإعدادات المركزية، دعم -x، offline+online) + قالب mako بترويسة عربية + الهجرة 0001_reference_tables (§31.1 حرفيًا بقصورها: الأعمدة/الأنواع/الافتراضات/الفهارس الفريدة/قيود الإيجابية) + 3 اختبارات integration خضراء بدورة صعود/هبوط/إعادة صعود وعقد "القاعدة تُترك عند head". القاعدة الحية الآن عند 0001_reference_tables (head).
- **قرارات موثقة:** (1) إضافة `sqlalchemy[asyncio]>=2.0` لمجموعة dev — إلزامية لعمل القالب غير المتزامن أصلًا (greenlet) وستحتاجها أي استخدام مستقبلي لـSQLAlchemy async؛ رافقها uv.lock في الالتزام لأن pyproject بلا قفله المحدث يكسر `uv sync --frozen` (مرحلة deps في Dockerfile 0.8). (2) إعادة كتابة الدرايفر postgresql://→postgresql+asyncpg داخل env.py (create_async_engine يرفض المجرد). (3) render_as_string(hide_password=False) بدل str(url) لتفادي إخفاء كلمة المرور. (4) أسماء قيود الهجرة مجردة البادئة لتتكامل مع خريطة التسمية بدل تضاعفها. (5) حجب integration من pytest الافتراضي عبر addopts (لا عبر conftest — العلامة مسجلة أصلًا في pyproject).
- **تنبيهات للوكلاء اللاحقين:** (أ) على الخادم الهدف: Dockerfile.engine يثبت alembic وحده بعد sync --no-dev — يجب أن يضيف سطر تثبيته greenlet معه (نفس الشرط الموثق أصلًا لـ0.8 بخصوص نقل alembic لتبعيات تشغيل)، وإلا ستفشل خدمة migrate هناك بـModuleNotFoundError: greenlet. (ب) عيب كامن في common/config.py خارج نطاقي: _ENGINE_ROOT=parents[3] يحل إلى engine/packages لا جذر engine → ملف engine/.env لا يُقرأ فعليًا (يعمل اليوم مصادفةً لأن الافتراضي يطابق قيمة .env) — يُراجع من صاحب الحزمة. (ج) مخالفات ruff في supervisor.py موجودة حتى في HEAD وتحجز بوابة `make gate` الكاملة — تُحسم من مالك 0.5.
- **نتائج الأوامر الحرفية:** ruff (نطاق المهمة) نجاح/نجاح؛ mypy: Success 39 ملفًا؛ lint-imports: 6 kept 0 broken؛ pytest: 186 passed, 3 deselected؛ pytest -m integration: 3 passed؛ alembic current: 0001_reference_tables (head)؛ supervisor health: 4/5 ✓ وmigrate SKIPPED (متوقع هذه الجلسة)؛ ruff كامل المستودع: فشل على supervisor.py وحدها (موجود مسبقًا حتى في HEAD).

---
Task ID: 1-b
Agent: candle-builder (full-stack-developer)
Task: المهمة 1.4 — منشئ الشموع الحدثي (CandleBuilder + bucket_floor) بشموع §8.1 كاملة الحقول وسياسة عدم إعادة الرسم §27

Work Log:
- قراءة السياق الإلزامي كاملًا: worklog (المهام 0→0.6) + Master Plan §8.1 (الشمعة بحقولها) + §27 كاملًا (فصل DEVELOPING/CONFIRMED عبر is_closed وجمود المقفلة) + §33.1 (موضع candle aggregator بعد event published) + §7.1/§26.3/§38.1 (عقد الوقت واللا-نظرة-المستقبلية) + schemas/market.py + schemas/enums.py + pyproject (البوابات الصارمة).
- كتابة services/ingestion/src/ingestion/candles.py: دالة bucket_floor للستة أطر (تقريب أرضي مطلق منذ epoch يصمد حتى لما قبل 1970، تطبيع الواعي إلى UTC، رفض الساذج والأطر غير المدعومة بValueError) + سلّل شدة الجودة QUALITY_SEVERITY_LADDER (الترتيب المنقول من تعريف 1.4 مع توثيق صريح أنه يخالف ترتيب تصريح enums.py في موضعي OUT_OF_ORDER/DUPLICATED وأنه قابل للمراجعة عند دمج 1-a) + class CandleBuilder: بناء لكل (instrument_id, timeframe) عبر dict مجارٍ داخلية، add_trade بعقد إرجاع ثلاثي موثق (None للأولى والمتأخر / مقفلة عند العبور / نسخة متطورة داخل الدلو)، close_current صريح لنهاية البث، وإحصاءات n_closed/n_evolved_updates/late_events/first/last bar_time كخصائص للقراءة.
- القيم المشتقة §8.1 تُحسب عند كل إصدار (حتى المتطورة) ومن أحداث وصلت فعلًا فقط؛ الأحداث المتأخرة بعد تجاوز نافذتها تُحصى ولا تمس المقفلة ولا تنشئ شمعة فائتة بأثر رجعي (آخر دلو مقفل محروس في حالة المجرى).
- كتابة tests/unit/test_candles.py: 44 اختبارًا — golden مضمّن كامل الحقول بقيم يدوية (قيم وسيطة للمتطورة ثم النهائية عند العبور ثم شمعة مسطحة بإقفال صريح) + حدود الأطر الستة عند العبور + المتطورة لا تفوّض + المتأخرة (بعد العبور وبعد الإقفال الصريح وفي دلو فجوة فائت) + المسطحة + true_range بفجوات صاعدة/هابطة تهيمن فيها مسافة القمة/القاع عن إغلاق الأمس + سلّل الجودة (QUARANTINED واحدة تجتاح الشمعة + كل الأزواج المتجاورة بترتيبي وصول) + مجريان مستقلان يتشاركان البنّاء + اللا-نظرة-المستقبلية صراحة (إدراج t+1 لا يغيّر مخرجات t: الإقفال بالعبور == الإقفال الصريح بايت-ببايت) + الحتمية بقائمة مختلطة مثبتة (إحصاءاتها محسوبة يدويًا: 3/5/2) + خاصيتا hypothesis بذر مثبتة (derandomize): تجميع دلو واحد لأي إطار (open/close/high/low/volume والمشتقات كلها) واستقلال مخرجات البادئة عن t+1.
- تصحيحات أثناء التطوير: SIM108 (صيغة شرطية لrealized_volatility) وS311 (استبدال random.Random باستراتيجيات hypothesis الصرفة وقائمة مثبتة حرفيًا) + اكتشاف دقيق: sum() في بايثون 3.12 جمعٌ معوَّض (Neumaier) قد يخلف التراكم اليساري بأولب واحد — الاختبار يطابق الخاصية الرياضية بapprox والمطابقة التامة مع التراكم الحدثي اليساري بترتيب الوصول.
- التحقق: ملفاتي خضراء 100% على البوابات الأربع (ruff format --check: 2 files already formatted · ruff check: All checks passed · mypy: صفر أخطاء في ملفاتي ضمن 48 ملفًا مفحوصًا · pytest: 44 passed). البوابات الكاملة على المستودع فشلت حصريًا في ملفات الوكيل الموازي النشط (binance.py/quality.py/refine.py/test_binance_adapter.py/test_refine.py/test_binance_live.py — ruff format ×4، ruff check ×6، mypy ×3، pytest ×3 فاشلة من 339 ناجحة) — أعدت المحاولة مرتين بعد انتظار والوكيل ما يزال يكتب؛ موثق هنا وليس من عمل هذه المهمة (lint-imports أخضر كليًا: 6 عقود محفوظة).
- commit 493eb8f من جذر /home/z/my-project بملفاتي فقط: candles.py (370 سطرًا) + test_candles.py (751 سطرًا) = 1121 إدراجًا.

Stage Summary:
- **المنتج:** منشئ شموع حدثي صرف بلا نظرة مستقبلية — عقد إرجاع موثق ثلاثي، مقفلات غير قابلة للتعديل أبدًا (§27)، متطورة لا تفوّض قرارًا حيًا، متأخرون يُحصون بلا صمت ولا شموع فائتة بأثر رجعي، وقيم مشتقة §8.1 تحسب من أحداث وصلت فعلًا فقط. bucket_floor مصدَّرة على مستوى الوحدة لاحتياج الآخرين إليها.
- **اتفاقيات الحواف الموثقة:** high==low ⇒ body_fraction=0.0 وclose_location_value=0.5؛ أول شمعة ⇒ true_range=high-low وما بعدها max مع مسافتي إغلاق الأمس (الفجوات مقصودة — جوهر TR)؛ realized_volatility خام |ln(close/open)| والتطبيع مكانه features مرحلة 2؛ open سعر أول حدث وصل وclose آخر حدث وصل (ترتيب وصول لا طوابع)؛ session_id تاريخ UTC بصيغة ISO (A-03).
- **قرارات معمارية:** (1) instrument_id = venue:symbol مشتق من الحدث (المفتاح الطبيعي المتسق مع فهرس 0.6 وfixtures schemas؛ الربط بUUID لاحقًا في التخزين). (2) timeframe من event.source_timeframe — خارج الأطر الستة يُرفع ValueError فوريًا بلا أثر جانبي. (3) close_current يستقبل (instrument_id, timeframe) صراحةً لانتفاء اللبس في بنّاء متعدد المجاري. (4) سلّل الجودة بترتيب المهمة 1.4 مع وسم «قابل للمراجعة عند دمج 1-a» وتوثيق خلافه عن ترتيب enums.py.
- **تحذير للوكيل الموازي/اللاحقين:** البوابة الكاملة لن تخضر قبل أن يُصلح الوكيل الموازي (1-a) ملفاته الخمسة؛ ملفات هذه المهمة لا تحتاج أي تعديل عند دمج 1.5/1.6 — الواجهة: add_trade/close_current/الإحصاءات + bucket_floor + QUALITY_SEVERITY_LADDER.

---
Task ID: 1.5
Agent: raw-store-builder (full-stack-developer) — أُتمم التسجيل بيد المنسق بعد انقطاع أمد الوكيل عند اكتمال العمل
Task: المخزن الخام (Parquet/S3 + ميتاداتا PG) + هجرة جداول السلاسل الزمنية §31.2

Work Log:
- قراءة السياق الكامل (worklog + §31.2 + schemas + هجرة 0001 + binance.py) ثم بناء الهجرة 0002_timeseries_tables: market_events (فهرس فريد جزئي (symbol, sequence_id) + فهرس (symbol, event_time)) + candles (PK (instrument_id, timeframe, bar_time) — الشمعة المتطورة تُحدَّث لا تُستنسخ) + raw_batches (سجل دفعات الميتاداتا).
- raw_store.py: RawStore بثلاث عمليات رئيسة (write_batch/read_batch/list_batches) + ensure_bucket idempotent — pyarrow zstd عبر asyncio.to_thread، minio-py كذلك، asyncpg مباشرة.
- قرارات موثقة في رأس الملف: حتمية بايتية (مخطط أعمدة ثابت بترتيب تصريح TradeEvent، فرز مستقر بالمفتاح الزمني فقط، لا طوابع كتابة في الملف)، md5 بusedforsecurity=False لسلامة التنزيل، بنية مفتاح يومية، قيد الاتساق (رفع قبل إدراج — اليتيم يُرصد لا يُكتم).
- تبعيات وقت تشغيل جديدة للحزمة: pyarrow>=17 + minio>=7.2 + asyncpg>=0.30 مع تحديث القفل.
- اختبارات: unit (بنية المفتاح، حتمية البايتات مرتين، round-trقق Parquet محلي بلا شبكة) + integration حية (ensure_bucket، كتابة/قراءة/تعداد/تنظيف ضد SeaweedFS وPG الفعليين) + هجرة 0002 صعود/هبوط/أعمدة.

Stage Summary:
- **الخام خالد في الكائني والقاعدة تعرفه:** أي دفعة aggTrades تُكتب Parquet مضغوطاً في engine-raw وتُسجل في raw_batches — بوابة «الخام خالد» للمرحلة 1 محققة.
- **الحتمية البايتية مثبتة اختبارياً** — نفس القائمة ⇒ نفس hash الملف (شرط بوابة الإعادة 1.6).
- **البوابة عند الالتزام:** make gate أخضر (360 passed) + 11 integration خضراء (هجرتان + مخزن حي + Binance حي) + alembic current عند 0002_timeseries_tables.
- **تركة للمرحلة 1.6:** كتابة candles/market_events عبر الجودة + توصيل worker الحي + make verify-phase1 (إعادة حتمية من الخام + مقارنة golden مع klines).

---
Task ID: 1.6 (+ إغلاق بوابة المرحلة 1)
Agent: Main Agent (Z.ai Code — Coordinator) + ingestion sub-agents
Task: اختبارات الجودة الشاملة + العينة المرجعية + المخزن السوقي + verify-phase1

Work Log:
- إنهاء عمل الوكيل المنقطع 1-a بنفسي: إصلاح اختبارين معيبين وسيناريو ثالث (مؤشر الترقيم = T آخر صفقة؛ متأخر بمعرف جديد؛ عدّ المفقود بشرط سابقة) + mypy — البوابة 360 خضراء ثم التزام 1-a و1-b (وكيل 1-b أكمل بنفسه: 44 اختباراً وcandles.py بإتقان).
- استلام عمل الوكيل المنقطع 1.5 (أكمل كل شيء قبل انقطاعه): هجرة 0002 + raw_store.py حتمي البايتات — تحققت من البوابة (360+11) والتزمته ووثقت قسمه في السجل.
- سكربت العينة المرجعية scripts/fetch_phase1_fixture.py: التقاط نافذة 10 دقائق BTCUSDT (3999 صفقة aggTrades + 10 شموع klines مرجعية) → fixtures/phase1 مثبتة git (trades.parquet 73KB + klines.json + manifest).
- candles.py: إضافة معامل الإطار الصريح (timeframe=) لبناء شموع 1m من أحداث tick "1t" — الفجوة المكتشفة بين 1-a (أحداث 1t) و1-b (بنّاء بإطار المصدر)؛ سلوك 1.4 الافتراضي محفوظ + 3 اختبارات جديدة.
- market_store.py: MarketStore — كتابة الأحداث المنقّاة idempotent (ON CONFLICT الجزئي) + upsert شموع (متطور→مقفول تحديث) + قراءة مرجعية؛ معرف أداة حتمي uuid5(venue:symbol) لعمود Uuid الإلزامي.
- scripts/verify_phase1.py + هدف make verify-phase1: البوابة الشاملة — الخلود (round-trip RawStore) + الحتمية (hash المسار الأرشيفي = hash الإعادة من الخام) + الذهبية (مطابقة OHLCV مع klines البورصة على الدلاء المكتملة) + القاعدة (idempotency + hash موحد).
- إصلاحات تشغيلية: Makefile استُعيد بعد تحويل أداة التعديل tabs→مسافات (درس: استخدم python للتعديل على ملفات حساسة للمحارف)؛ اختبار حي هش (len==10) رُخّي إلى نطاق واقعي.

Stage Summary:
- **بوابة المرحلة 1 مغلقة رسمياً:** `make verify-phase1` أخضر كاملاً — العينة المرجعية 3999 صفقة: الحتمية hash-for-hash (0841ff8b…)، الذهبية 9/9 دلاء مكتملة مطابقة لشموع البورصة 100%، الخام خالد round-trip، القاعدة 3999 حدث idempotent + 10 شموع hash موحد.
- **الحصيلة الكلية للمشروع حتى الآن:** 376 اختباراً (363 unit/property + 13 integration) — بوابة make gate خضراء بالكامل.
- **قرارات جديدة موثقة:** الإطار الصريح للبنّاء (tick→1m دون مس عقد الحدث)؛ جودة الحدث المخزن من إشاراته الحدثية البحتة (لا الحالات الكسولة المعتمدة على الساعة)؛ market_events للمنقّى لا للمكرر؛ الدلو المقصوص آخر النافذة خارج حكم الذهبية (مؤجل لا فاشل).
- **التالي:** المرحلة 2 (التقلب والجلسات والسياق) — حزمة math، محرك التقلب §16، الجلسات، انظام HTF §9.2-9.4، مِحور الاستئصال، لقطة حالة السوق.

---
Task ID: R-1 (استرداد البيئة بعد إعادة إقلاع المنصة)
Agent: Main Agent (Z.ai Code — Coordinator)
Task: مراجعة التقدم المطلوبة من المالك + استرداد البيئة التي ماتت بين الجلسات وإعادة إثبات البوابات

Work Log:
- تشخيص حالة ما بعد الإقلاع: venv المحرك فُرغ، وكل من خادم dev والمشرف والخدمات التحتية ميتة، وثنائيات infra/local/bin (postgres/nats/seaweedfs) محية من القرص بينما عنقود data/pg أعيدت تهيئته فارغاً.
- استعادة venv بـ uv sync --all-packages ثم إعادة تزويد الثنائيات عبر make infra-provision: nats 2.10.24 وpostgres 16.4 (Zonky) نجما، لكن seaweedfs فشل بـ401 من Docker Hub.
- تشخيص جذري بالتجربة اليدوية: token وفهرس OCI وmanifest كلها تعمل؛ الطبقة (blob) هي التي تُرد بـ401 — Docker Hub بات يفرض Bearer على طلبات الطبقات نفسها. أُصلح provision.sh بدالة download_auth تمرر الرمز (الالتزام cc6949c) وثُبّتت الثنائية 4.47 يدوياً من الطبقة المنزلة.
- مطابقة الأسرار: .env أُعيد إنشاؤه من المثال (engine-secret-change-me) بينما s3-config.json الناجي في data/seaweed يحمل engine-secret — عولجت بمواءمة .env (بيانات العنقود الكائني الناجية أهم من المثال).
- إطلاق الأغلفة بنمط double-fork (ADR-002): engine-infra (المشرف 2907: postgres/nats/seaweedfs/migrate/worker — كلها ✓) وengine-api (uvicorn :4001 — healthz 200). خادم Next.js تعيد المنصة إدارته ذاتياً (pid 1116).
- إعادة إثبات البوابات كاملة: make gate — 363 passed + 6 عقود حدود محفوظة؛ pytest -m integration — 13 passed؛ make verify-phase1 — خضراء بالكامل (الحتمية 0841ff8b… والذهبية 9/9 والقاعدة idempotent 3999+10)؛ alembic عند 0002_timeseries_tables.

Stage Summary:
- **البيئة مستردة بالكامل والبوابات مثبتة من جديد**: لا خسارة لأي كود أو عينات (كلها في git) — الفاقد الوحيد كان بيانات القاعدة/الكائن القابلة لإعادة البناء من العينة المرجعية، وقد أُعيد بناؤها فعلياً بverify-phase1.
- **درس بيئي جديد موثق**: إعادة إقلاع المنصة تمحو venv وثنائيات infra/local/bin و.env (المتجاهل) — بروتوكول الاسترداد: uv sync → make infra-provision → مواءمة S3_SECRET_KEY مع s3-config.json الناجي → إطلاق الأغلفة. وأصل جذر PX مُصلح في الالتزام cc6949c.
- **حالة الخطة**: المرحلتان 0 و1 مغلقتان ومثبتتان؛ التالي المرحلة 2 (التقلب والجلسات والسياق) وفق build_plan §D.

---
Task ID: 2-a
Agent: math-builder (full-stack-developer)
Task: المهمة 2.1 — حزمة quantmath: ATR ومئينيات متدحرجة وز-scores وتشبع

Work Log:
- قراءة السياق الإلزامي كاملًا: worklog.md (المرحلتان 0 و1 مغلقتان)، §16 Volatility Engine (سطور 978-1002)، build_plan المرحلة 2 سطر 2.1، عقود import-linter (سطور 140-215)، pyproject حزمة engine-math، ونمط اختبارات الخصائص في test_schemas_bounds.py/test_candles.py.
- بناء الحزمة النقية في packages/math/src/quantmath/ — 6 موديولات، 15 دالة علنية، استيراد numpy فقط (لا schemas ولا common ولا أي حزمة مشروع — عقد "quantmath is a foundation"):
  - _internal.py: اسم النوع FloatArray (PEP 695) + as_f64_1d (إجبار float64 أحادي البعد) + check_window.
  - rolling.py: rolling_mean/rolling_std(ddof)/rolling_zscore/rolling_percentile — إحصاء لكل نافذة على حدة (لا مجاميع جارية) ليطابق np.mean/np.std حرفيًا بايت-بايت.
  - atr.py: true_range (فجوات الإغلاق السابق) + wilder_atr (RMA: بذرة متوسط ثم استدعاء ذاتي) + atr_percentile (تفويض للمئيني).
  - volatility.py: realized_volatility + range_expansion_percentile + vol_of_vol (حارس |mean|<1e-12) + gap_shock (معيارية بالـATR) + expected_holding_vol (جذر الزمن) + spread_to_range.
  - saturation.py: saturation_run (عدّ متتالٍ مع عقد nan) + is_saturated (boolean).
  - __init__.py: إعادة تصدير كاملة بـ__all__ مرتب (RUF022) + __version__.
- قرارات العقود الموثقة في docstrings: النوافذ الخلفية شاملة للقيمة الحالية؛ المئيني = عدد الأصغر قطعيًا ÷ (الأعضاء غير الـnan − 1) فأفضل/أسوأ حالة 1.0/0.0 والتساوي التام ⇒ 0.0؛ nan الحالية ⇒ nan وعناصر nan الأخرى داخل النافذة تُستبعد (بسطًا ومقامًا) بينما inf تمر كما هي دون انفجار؛ حارس z-score: أي std محسوب = 0 ⇒ nan (اكتشف أثناء الخصائص: انهدام تحت-عادي لمربعات الانحرافات يعطي std=0 مع فرق≠0 ⇒ كان سيولد inf)؛ spread_to_range عند range=0 ⇒ 0.0 دائمًا؛ gap_shock[0]=nan وatr=0 مع فجوة>0 ⇒ inf؛ saturation: nan في الموضع ⇒ nan ويقطع الركض؛ expected_holding_vol: horizon صحيح ≥ 1 وإلا ValueError.
- 84 اختبارًا جديدًا: 16 (ATR) + 22 (rolling) + 28 (volatility) وحدةً بقيم محسوبة يدويًا (وايلدر بخطوات ثنائية التمثيل تقارن حرفيًا ==)، و18 خاصية derandomize: لا-نظرة-مستقبلية (تعديل الذيل لا يمس خرج البادئة) لكل العائلات الأربع، حتمية بايت-بايت (tobytes) على مدخلات فيها nan/inf، نطاقات (ATR≥0، مئينيات∈[0,1]، |z|≤√(window−1)، spread∈[0,1])، رتابة المئيني، مرجع saturation يدوي مستقل، وتركيب √(a·b)=√a·√b لتحجيم الاحتفاظ.
- إخماد تحذيرات numpy الصامتة (errstate) في كل مسارات التمرير غير المحدود كي يظل "تمرير بلا انفجار" صامتًا حقًا.

Stage Summary:
- **المنتج**: quantmath 0.1.0 جاهزة كأساس نقي لمحرك التقلب (2.2) — 15 دالة علنية على float64 حصرًا، نوافذ خلفية شاملة، حتمية صرفة، دافئ موضعي nan، عقود nan/inf موثقة لكل دالة. الالتزام d7421b8 (10 ملفات، 1421 سطرًا).
- **البوابات لملفاتي حرفيًا**: ruff format --check "10 files already formatted" ✓، ruff check "All checks passed" ✓، mypy strict "Success: no issues found in 65 source files" (كلها بما فيها ملفاتي العشرة — صفر أخطاء؛ فشل سابق عابر بملف الوكيل الموازي test_sessions.py:208 زال قبل إعادة الفحص) ✓، pytest للملفات الأربعة "84 passed in 2.31s" ✓، lint-imports "Contracts: 6 kept, 0 broken" — quantmath ما زالت أساسًا نقيًا ✓.
- **القرارات الحرجة للوكلاء اللاحقين**: rolling_std/realized_volatility بـddof=1 (المقارنة المرجعية np.std(..., ddof=1))؛ atr_percentile على سلسلة ATR ذات دافئ nan تعمل مباشرة (الاستبعاد) فلا حاجة لتقطيع المتصل؛ expected_holding_vol تقبل numpy-int لكنها ترفض float مثل 2.5؛ مقايضة الأداء المتعمدة: إحصاء لكل نافذة O(n·w) مقابل مطابقة مرجع numpy حرفيًا.

---
Task ID: 2-b
Agent: sessions-builder (full-stack-developer) — أُتمم التسجيل بيد المنسق بعد انقطاع أمد الوكيل عند اكتمال العمل والالتزام
Task: المهمة 2.3 — وحدة الجلسات: يوم UTC + نوافذ سلوكية + بنية الفتح (§9.4/§9.5، A-03)

Work Log:
- (من المنسق) الوكيل انقطع لأسباب المهلة بعد أن أنجز كامل العمل والتزمه في de2b875 — تحققت من البوابات بنفسي وأثبتّها أدناه.
- sessions.py (812 سطرًا): SessionWindow/SessionWindowsConfig بنوافذ سلوكية إعدادية (آسيا 00-08، أوروبا 07-16، أمريكا 13:30-20) بدلالة [بداية، نهاية) عبر دقائق UTC ودعم العابر لمنتصف الليل + خطر الانتقال عند الحواف + نوافذ صيانة.
- OpeningStructure (§9.5): فجوة مقابل إغلاق الأمس + مدى افتتاحي (30د إعدادي) + initial balance (60د) + دافعة افتتاح (PENDING/UP/DOWN/REVERSAL بعتبة نسبية من المدى الافتتاحي) + علاقة الإغلاق السابق — بلا افتراض سد الفجوة أو استمرار الدافعة، وبلا أي ثابت سعري مطلق.
- SessionTracker الحالة الموضعية: عقد شمعة الجلسة السابقة المتأخرة (تحدث جلستها لا الحالية)، إقفال يوم UTC يثبت prior_* للجلسة التالية، بلا نظرة مستقبلية (مثبتة اختبارًا بمقارنة قائمة كاملة مقطوعة عند k مقابل قائمة مقطوعة أصلًا).
- المؤجل الموثق صراحة: تشكل السيولة المبكرة (مرحلة 3) واختلال الافتتاح (مرحلة 4).
- test_sessions.py (992 سطرًا): 75 اختبارًا — حدود منتصف الليل، حواف النوافذ حرفيًا، التقاطعات، DST معدوم، الفجوات الثلاثية، اكتمال المدى الافتتاحي، الدافعة والانعكاس، الترتيب المعكوس جزئيًا، لا-نظرة-مستقبلية.

Stage Summary:
- **البوابات (تحقق المنسق بعد الالتزام):** pytest test_sessions.py = 75 passed · ruff format/check نظيفان · mypy Success 65 ملفًا · lint-imports 6 عقود محفوظة · المجموع الكلي 522 passed + 13 deselected.
- **الالتزام de2b875**: sessions.py + test_sessions.py فقط (1804 إدراجًا).
- **جاهز لـ2-c**: طبقة features ستستهلك الجلسات لاحتياج لقطة الحالة إليها.

---
Task ID: 2-c
Agent: features-builder (full-stack-developer) — أُتمم التسليم والتوثيق بيد المنسق بعد انقطاع أمد الوكيل عند اكتمال العمل
Task: المهمة 2.2 — حزمة السمات features (المسار الوحيد A-02) + محرك التقلب الموضعي لكل (أداة، إطار) (§16)

Work Log:
- (من المنسق) الوكيل أنجز كامل الشيفرة لكن انقطع قبل الالتزام — أنهيتُ التدقيق والإصلاحات الثلاثة والالتزام بنفسي.
- features/windows.py: استخراج المصفوفات من list[Candle] بتحقق صارم (أداة/إطار واحد، ترتيب تصاعدي، رسائل عربية بالموضع الأول) + log_returns يدويًا. السمات تقرأ OHLCV الخام وحده (اختبار يحقن range/body مخزنة كاذبة ويثبت عدم الثقة بها).
- features/vol_features.py: 12 دالة سمات جسرًا نظيفًا فوق quantmath (atr/atr_pct/realized_vol/vov/gap_shock/spread_to_range/expected_holding_vol/range_expansion + normalized_range/directional_efficiency/volume_concentration تحضيرًا لـ2-d) — اختبار الجسر يطابق خرج السمة بنداء quantmath المباشر بايت-بايت.
- features/registry.py: السجل المركزي الحتمي (11 سمة بأسماء حرفية مثبتة، FeatureCategory الأربع، default_params محفوظة MappingProxyType، compute_feature بالاسم مع تجاوزات مُتحقق منها) — الدليل الحصري لمِحور الاستئصال (2-e).
- market_state/volatility.py (490 سطرًا): VolatilityConfig/VolatilityState/VolatilityEngine — عقود موثقة: شموع مغلقة فقط (is_closed=False ⇒ ValueError)، المتأخرة تُحصى ولا تغير الحالة (late_ignored)، التكرار المحتجز ⇒ ValueError، لا-نظرة-مستقبلية خاصيةً، مخزن دوّار بطول history_bars.
- **العتبات التطبيعية (جوهر بوابة المرحلة 2)**: ThresholdKey (7 مفاتيح: STRUCTURAL_LEVEL_BUFFER/DISPLACEMENT_MIN/SWEEP_TOLERANCE/WICK_BREAK_TOLERANCE/ZONE_PROXIMITY/ENTRY_ZONE_HALF_WIDTH/TARGET_ZONE_HALF_WIDTH) + DEFAULT_MULTIPLIERS محفوظة — threshold() = atr × multiplier حصرًا، بلا أي مسار سعري مطلق؛ الاختبار يثبت مضاعفة ATR تضاعف العتبة خطيًا.
- إصلاحات المنسق بعد الانقطاع: (1) list_features كان يعيد أزواج (مواصفة، دالة) بدل المواصفات — أصلح المولد؛ (2) اختباران يبنيان شموعًا OHLC غير صالحة عرَضًا (إغلاق خارج [low,high]) أعيدت صياغتهما بمدى صريح صالح مع بقاء القصد (خرق الترتيب/العوائد)؛ (3) توقع دافئ خاطئ في expected_holding_vol_manual (عنصري لا آخر-عنصر) صُحح وفق العقد الموثق؛ (4) 4 أخطاء mypy (تعليقات type: ignore[misc] للجمود المتعمد + تعليق إرجاع + Callable بدل object).
- البوابات (تحقق المنسق): pytest ملفات المهمة = 175 passed · mypy Success 74 ملفًا · ruff format/check نظيفان · lint-imports 6 عقود محفوظة · المجموع الكلي 697 passed + 13 deselected.

Stage Summary:
- **المسار الوحيد A-02 قائم**: features هي طبقة السمات الصرفة الوحيدة (لا حالة، لا I/O) — الحي والإعادة سيستدعيانها حصرًا؛ السجل المركزي جاهز لتغذية الاستئصال (2-e) والنظام (2-d).
- **محرك التقلب §16 مكتمل**: كل مقاييس الفقرة السابعة + العتبات التطبيعية بعقد موثق واختبارات خصائص (بادئة مستقلة عن الذيل، حتمية بين محركين).
- **الالتزام**: ملفات 2-c حصرًا (3140 سطرًا منها 2025 اختبارات) — رقم الالتزام بعد التنفيذ.
- **جاهز لـ2-d/2-e**: العتبات التطبيعية والسمات (directional_efficiency/normalized_range/volume_concentration/range_expansion) متاحة لمحرك النظام والاستئصال.
---
Task ID: 2-e
Agent: ablation-builder (full-stack-developer)
Task: المهمة 2.5/2-e — هيكل مِحور الاستئصال (§43): جدول base/±feature فارغ الوظائف مكتمل التوصيل

Work Log:
- apps/replay/src/engine_replay/ablation.py (جديد، 383 سطرًا): FeatureSet/Dataset/AblationVariant/AblationSpec/AblationResult/AblationReport/VariantKind كلها frozen؛ الأسماء تتحقق ضد سجل السمات حصرًا (رفض عربي للمجهول والمكرر في القاعدتين).
- الدلالة الموثقة: base=مجموعة البدء، ablated=المختبرة بُعزلًا — X∉base ⇒ plus_X، وX∈base ⇒ minus_X (لا plus لعضو حاضر: تكرار بلا معلومة — رفض صريح بValueError عربية)؛ الجدول: base ثم كتلة plus ثم كتلة minus بترتيب ablated.
- نقطة الحقن الوحيدة MetricEvaluator (الافتراضي placeholder_evaluator = عدد السمات حصرًا — لا مقاييس وهمية)؛ run_ablation يحسب كل سمة في كل متغير فعليًا عبر compute_feature (توصيل حقيقي + حارس طول السلسلة = عدد الشموع).
- الحتمية: to_json بايت-بايت (sort_keys/indent=2)؛ created_at_utc الاستثناء الوحيد؛ now المحقون مصدر الطابع والقياس معًا (ساعة ثابتة ⇒ elapsed_ms=0.0) فتصبح الحتمية كاملة.
- scripts/run_ablation.py: --dataset phase1 (الوحيد) يبني الشموع من fixtures/phase1 بنمط verify_phase1 حرفيًا (read_parquet_bytes→تنقيح→جودة→CandleBuilder 1m)؛ افتراضي: قاعدة = كل غير-VOLATILITY (5 سمات)، عزل = فئة VOLATILITY كاملة (6)؛ يطبع جدول markdown ويكتب JSON+MD في data/research/ablation/.
- Makefile: هدف ablation-dryrun + إضافته إلى .PHONY — تحذير التبويبات تحقق فعلًا: أداة التحرير حوّلت تبويبات الملف كله مسافات، فاستعدته من git وأعدت اللصق بسكربت بايت-آمن.
- tests/unit/test_ablation.py: 38 اختبارًا — البنية والرفض العربي وplaceholder والحتمية البايتية بساعة محقونة وnan الدافئ لا يفجر المحور (window=100 على 6 شموع ⇒ nan كاملة) وحارس التوصيل (monkeypatch بطول مخالف) وجدول مختلط كامل.

Stage Summary:
- **البوابات حرفيًا**: ruff format "5 files already formatted" ✓ · ruff check "All checks passed!" ✓ · mypy "Success: no issues found in 78 source files" ✓ · pytest "38 passed" ✓ · lint-imports "Contracts: 6 kept, 0 broken" ✓ · make ablation-dryrun نجح: 10 شموع 1m، 7 متغيرات (base + 6 plus لسمات VOLATILITY)، تقرير JSON+MD مكتوب في data/research/ablation/ ✓. المجموع الكلي 735 passed + 13 deselected.
- **جاهز لـ5a.3/9**: حقن مقاييس الإعادة الحقيقية عبر MetricEvaluator يفعّل بوابات الترقية §41 (التقرير يحمل spec_name/البيانات/السمات/المقاييس/الزمن) دون مساس بنية الجدول.
---
Task ID: 2-d
Agent: regime-builder (full-stack-developer)
Task: المهمة 2.4/2-d — مصنف نظام السوق (§9.3) + انحياز HTF (§9.2) كحالتين موضعيتين حتميتين

Work Log:
- قرأت السياق الإلزامي (worklog 2-a/b/c، §9 كاملًا، build_plan سطر 2.4، volatility.py/registry/vol_features) ثم بنيت ملفين جديدين فقط + تصدير __init__: **لا حساب سمات داخل المصنف إطلاقًا** — RegimeFeatures/HtfBiasInputs يملؤهما المستدعي من features/VolatilityState (فصل مسؤولية يجعله قابلًا للإعادة المعزولة).
- regime.py (404 أسطر): REGIME_RULES_DOC جدول القرار الموثق (7 قواعد بأولوية صارمة + UNKNOWN)؛ بوابة تأكيد confirm_bars متتالية (hysteresis — قطع السلسلة يصفّر العد)؛ TRANSITION مموه عمدًا لا يثبت أبدًا (مصيد الغموض)؛ أي None ⇒ UNKNOWN للتحديث حصرًا مع حفظ النظام المؤكد داخليًا وقطع السلسلة؛ قرارات موثقة: atr_pct_mid مشتق (low+high)/2، volume_concentration مؤكد توسع ثالث في قاعدة 2، حقل إضافي gap_shock_atr=3.0، normalized_range يُحمل ويبوّب النقص بلا دخول في الجدول.
- htf_bias.py (289 سطرًا): وكيل مرحلي موثق صراحة (§9.2 الكامل يأتي من محرك البنية مرحلة 3 — الواجهة مصممة لاستبدال التغذية دون تغيير المستهلك)؛ «سياق لا مشغل» في الرأس؛ الكفاءة+إشارتها تقودان والوكلاء (nrange/atr_pct/displacement_proxy) يغلقون بوابة الاكتمال؛ تذبذب متكرر (انعكاسات متناوبة transition_flips=2) يفرض قراءة TRANSITION ويثبت بخمس متتاليات بخلاف النظام §9.3 — عدم التماثل موثق ومقصود.
- 128 اختبارًا (78 نظام + 50 HTF): حالات نقية لكل قاعدة، أولوية الصدمة، hysteresis بثلاثته، TRANSITION لا يثبت، None بعقوده، حتمية بايت-بايت (repr متطابق) بين محركين، لا-نظرة-مستقبلية (بادئة k مستقلة عن الذيل)، تدقيق عتبات نسبي يرفض الثوابت السعرية (< 10.0 وقيم على مقاس ticks ترفض).

Stage Summary:
- **البوابات حرفيًا**: ruff format "7 files already formatted" ✓ · ruff check "All checks passed!" ✓ · mypy "Success: no issues found in 80 source files" ✓ · pytest الملفين "128 passed in 0.93s" ✓ · lint-imports "Contracts: 6 kept, 0 broken" ✓ — والمجموع الكلي 863 passed + 13 deselected بلا انحدار.
- **الالتزام ef7316a**: 5 ملفات (1562 إدراجًا) حصرًا. جاهز لـ2-f: لقطة حالة السوق تستهلك RegimeState/HtfBiasState مع VolatilityState والجلسات.
---
Task ID: 2-f
Agent: snapshot-builder (full-stack-developer)
Task: المهمة 2-f — هجرة market_states (§31.3) + بنّاء لقطة حالة السوق + ناشر NATS (§32) + اختبارات مستهلك وتخزين حية

Work Log:
- migrations/0003_market_states.py (94 سطرًا): جدول market_states بأعمدة uuid/timestamptz وVARCHAR فوق أطوال التعدادات، payload JSONB، قيد مئيني، فهرس فريد (هدف ON CONFLICT) + فهرس أحدث-لقطة DESC — كلها عبر خريطة التسمية نفسها.
- **قرار مقياس موثق**: قيد volatility_percentile على [0,100] لا [0,1] — نوع Percentile في schemas نفسه (ge=0, le=100) ومثال §32 (62.4)، وcompute_market_volatility_summary يوثق أن التحويل [0,1]←[0,100] مسؤولية طبقة الدمج هذه (بنّاء اللقطة يضرب في 100).
- snapshot.py (129): SnapshotInputs مجمّد + build_snapshot حتمي بايت-بايت — الصمت عن الجودة الكسولة (غير-كافٍ ⇒ 0.0 بلا إسقاط)، وsession_id عقد صيغة عند المصدر لا يدخل النموذج (المخطط additionalProperties:false) ويُشتق من event_time عند التخزين.
- store.py (157): MarketStateStore على asyncpg يستقبل conn من المستدعي (لا يفتح اتصاله) — upsert_snapshot ‏idempotent عبر ON CONFLICT DO UPDATE، latest_snapshot يعيد البناء عبر pydantic (instrument من الحمولة: uuid5 أحادي الاتجاه)، count_snapshots. ترميز uuid5 نفسه الذي في ingestion مثبتًا بالمساواة المباشرة (بلا اعتماد بنيوي بين الطبقتين المتكافئتين).
- publisher.py في worker (105): SnapshotPublisher رفيع — بروتوكول هيكلي بدل استيراد nats، تنظيف الأداة لرمز موضوع قانوني، رؤوس event_type/schema_version، بث model_dump_json + flush، لا إعادة اتصال ولا تراجع (موثق). __main__: تشغيل تجريبي واحد قبل النبض يبث مثال §32 حرفيًا (ثُبت حيًا: published:market.state.example.5m.updated) بلا مساس بحلقة النبض.
- jsonschema مضافة لمجموعة dev (uv add --dev jsonschema types-jsonschema — توثيق الغيتس).
- الاختبارات: test_snapshot.py (59) وtest_publisher.py (18) شاملة jsonschema ضد المخطط المصدَّر؛ test_market_states_live.py (4): هجرة (أعمدة/فهارس/قيود عبر information_schema وpg_indexes وpg_constraint) + مخزن حي (idempotent/أحدث لا يمس القديم/DO UPDATE/عمود الجلسة والحمولة) + مستهلك NATS حي بموضوع معزول test-2f (رؤوس + مخطط + تفك back) + هبوط/صعود.

Stage Summary:
- **البوابات حرفيًا**: ruff format "14 files already formatted" ✓ · ruff check "All checks passed!" ✓ · mypy "Success: no issues found in 86 source files" ✓ · pytest الملفين الوحدوية "77 passed" ✓ · lint-imports "Contracts: 6 kept, 0 broken" ✓ · alembic current "0003_market_states (head)" ✓ · الحية "4 passed" ✓ · المجموع "940 passed, 17 deselected" (863+77) ✓.
- **ملاحظة خارج النطاق (قائمة قبل التغيير — أثبتُها بـgit stash)**: test_migrations*.py القديمة تفشل في تشغيل التكامل الكامل لأنها تدبس «head == مراجعتها» وتقادمت مع كل هجرة أحدث — تُترك لمعالجة لاحقة خارج نطاق هذه المهمة.
- **الالتزام ca675f2**: 12 ملفًا (1598 إدراجًا). جاهز للمرحلة التالية: توصيل بنّاء اللقطة في خط الابتلاع الحي مع SessionTracker.

---
Task ID: 2-g (+ إغلاق بوابة المرحلة 2)
Agent: Main Agent (Z.ai Code — Coordinator)
Task: بوابة خروج المرحلة 2: العينة المرجعية الثلاثية + verify-phase2 + توثيق وإغلاق

Work Log:
- إصلاح اختباري الهجرات القديمين المتقادمين (كانا يدبسان head == مراجعتهما): مساعد _alembic_head() يشاور alembic نفسه — 10 اختبارات تكامل خضراء (ADR-019).
- scripts/fetch_phase2_fixture.py: التقاط يوم UTC كامل BTCUSDT بثلاثة أطر — 1440×1m + 192×15m + 168×1h شموع klines مرجعية مثبتة git (334KB) + manifest بالهاشات.
- scripts/verify_phase2.py + هدف make verify-phase2: مسار السياق الكامل (جلسات ← تقلب ← نظام ← انحياز ← لقطة) على الأطر الثلاثة بسبعة فحوص صارمة.
- إصلاحات أثناء التطوير: خطأ أحادي في مقارنة البادئة (البادئة تنتج k−1 حالة)، موضوع اشتراك NATS الفعلي (btcusdt لا وهمي)، ونمط ترويسة ruff E402 (أي إسناد قبل sys.path.insert يكسر إتاحة ruff — الحل inline كنمط phase1).
- التوثيق الحي: progress.md جدول المرحلة 2 + بوابتها وسجل الجلسات؛ decisions.md: ADR-013..019؛ النسخ إلى engine/docs.
- البوابات النهائية: make gate كاملة = 940 passed + 6 عقود محفوظة + mypy 86 ملفًا نظيفًا؛ make verify-phase2 خضراء بالكامل.

Stage Summary:
- **بوابة المرحلة 2 مغلقة رسميًا**: `make verify-phase2` — الحتمية (6fbdc7b5e7f035bb… عبر مسارين) + لا-نظرة-مستقبلية على بيانات حقيقية (1429 حالة بادئة مستقلة عن الذيل) + العتبات التطبيعية (threshold/atr ≡ المضاعف حصرًا عبر 7 مفاتيح وكل شمعة) + تتابعات موثقة (نظام 1m وصل 6 حالات مختلفة عبر اليوم؛ انحياز 1h UNKNOWN→NEUTRAL؛ الجلسة الكاملة 09-25) + بث NATS حي وتخزين idempotent.
- **حصيلة المرحلة 2**: 577 اختبارًا جديدًا (84+75+175+128+38+77 وحدوي/خصائص + 4 تكامل حية) — المجموع الكلي 940 + 17 تكامل مؤجلًا؛ هجرة 0003؛ حزمتان جديدتان مكتملتان (quantmath، features) ومحركات أربعة في market_state (تقلب/نظام/انحياز/لقطة) ومحور استئصال موصول.
- **التالي**: المرحلة 3 — السيولة والبنية (SMC): swings، BOS/CHoCH، displacement، FVG، OB، premium/discount (§11)، وخريطة السيولة وأهدافها (§10).

---
Task ID: 3-a
Agent: Subagent (3-a — schemas البنيوية والسيولة)
Task: أسس المرحلة 3 المشتركة في schemas — كائنات البنية (§11) والسيولة (§10) وحمولات أحداث §20 الخمسة عشر + سجل EVENT_PAYLOAD_MODELS + مفتاح عتبة EQUAL_LEVEL_TOLERANCE + تبعيات الكاشفين.

Work Log:
- قراءة السياق الإلزامي كاملة: worklog (0→2-g)، Master Plan §10.1-10.5 و§11.1-11.8 و§20 و§31.3 و§32 حرفيًا، build_plan المرحلة 3، عقود import-linter (عقد «كاشفات مستقلة» يفرض أن الكائنات المشتركة تسكن schemas)، وكل الملفات المرجعية المنصوصة: market.py/enums.py/envelope.py/evidence.py/scenario.py/_types.py/export.py + الاختبارات الثلاثة النموذجية.
- إنشاء packages/schemas/src/schemas/structure.py: أساس `_StructureModel` (frozen + extra="forbid") + 7 تعدادات StrEnum موثقة المبررات (SwingDirection HIGH/LOW قطبية المتطرف بلغة §10.1/§20 لا LONG/SHORT، SwingScope ببقاء اسم الحقل الحرفي external_or_internal، BreakDirection، FvgDirection، FvgState=CREATED وحدها — البث هو التكوين والملء/الإبطال حالة كاشف تتبعية لأن «لا يُفترض أن كل فجوة تُملأ»، StructureConsequence من خطوة §11.6 الثالثة، PremiumDiscountSide) + Swing (السبعة الحرفية §11.1 + الامتداد الموثق الوحيد bar_time بعلاقته القانونية confirmation_time = bar_time + تأخير التأكيد) + 5 حمولات (StructureBreakPayload تخدم الأنواع الثلاثة مع choch_prior_direction=None لغير CHOCH، DisplacementEventPayload بالسمات الست الحرفية §11.4، FvgEventPayload، OrderBlockEventPayload بخطوات الأنابيب §11.6، PremiumDiscountEventPayload بنطاق معرّى بإلزام range_name).
- إنشاء packages/schemas/src/schemas/liquidity.py: أساس `_LiquidityModel` + 3 تعدادات (LiquiditySide بقوائم §10.1 منقولة نصًا داخل docstring، LiquiditySourceType بقرار موثق: «repeated highs/lows» و«untested external liquidity» خصيصتان تقاسان عبر test_count والحالة لا نوعا مصدر، ZoneState لدورة الحياة §31.3) + LiquidityZone بحقول §10.2 الاثني عشر الحرفية + الامتدادات الثلاثة (instrument/timeframe/state) مع model_validator للفاصل المرتب (price_low ≤ price_high — price_low == price_high جائز لمستوى معزول) + SweepEventPayload (شرط 3 §10.4 عبر penetration_reached وclassification للتقرير الذاتي دائمًا CONFIRMED_SWEEP عند البث) + BreakAcceptEventPayload («Acceptance ratio» §20).
- envelope.py: EVENT_PAYLOAD_MODELS بخمسة عشر نوعًا بنيويًا/سيوليًا حصرًا (موثق أن الطور اللاحق يوسعها وأن None إعلان صريح) + payload_model_for؛ __init__.py بإعادة تصدير كاملة (28 اسمًا جديدًا بترتيب RUF022 الحتمي)؛ export.py بتسجيل 9 نماذج جذور جديدة بمراجع فقراتها → إعادة توليد generated/ (24 مخططًا بدل 15 + index.json + README.md) وتثبيتها في الالتزام.
- volatility.py: مفتاح EQUAL_LEVEL_TOLERANCE موثقًا (§10.1 equal highs/lows + §11.6 compact opposing cluster) بقيمة افتراضية 0.25 في DEFAULT_MULTIPLIERS — الاختبارات القائمة تكرر على ThresholdKey ديناميكيًا فبقيت خضراء دون تعديل (تحقق فعلي: 48 passed). pyproject لـ structure و liquidity: إضافة engine-market-state (طبقة الكاشفات فوق السياق في هرم §47) — بلا uv lock/sync كما نُص.
- tests/unit/test_schemas_structure.py: 80 اختبارًا بنمط test_schemas_models.py — round-trip JSON لكل نموذج + عقد الوقت (ساذج مرفوض/واعي يطبَّع) + الحقول الحرفية §11.1/§10.2 كمجموعات مستقلة + قيم التعدادات العشر كثوابت مرجعية + الحدود (UnitInterval/موجب/عدد غير سالب) + الفواصل المعكوسة الثلاثة ترفض + نطاق المعالجة المنحل يرفض + normalized_distance يجوز تجاوز ±1 خارج النطاق + الجمود والحقول الغريبة + سجل الحمولات (15 حصرًا، كلها BaseModel، ABSORPTION_BUY/HTF_* → None، التمركز الذاتي بكل حمولة) + بوابة التصدير (check()==0 على generated/ + index يغطي 24 + كل مثال يمر jsonschema ضد مخططه المُصدَّر بنمط 2-f).
- البوابات النهائية الحرفية: export write ثم check = OK 24 مخططًا بايت-بايت؛ pytest الكامل = 1020 passed + 17 deselected (كان 940 — +80 جديدًا بلا انحدار)؛ اختبارات المهمة المستهدفة = 231 passed؛ ruff format --check كامل المستودع = 106 ملفات منسقة؛ ruff check = All checks passed؛ mypy strict (الأمر القانوني `uv run --no-sync mypy` بملفات pyproject) = Success 89 ملفًا — ملاحظة: استدعاء mypy بمسارات صريحة كما في نص المهمة يفشل عابرًا ب«features missing py.typed» في وضع المسارات خارج تكوين pyproject، فالأمر القانوني (نمط make gate) هو المرجع وقد خضر؛ lint-imports = 6 عقود محفوظة 0 مكسورة (schemas ما زالت ورقة نقية).
- الالتزام e4ec813 (20 ملفًا، 2058 إدراجًا): المخططين الجديدان + envelope/__init__/export + 9 مخططات مولدة + index/README + volatility + pyproject للكاشفين + الاختبار الجديد.

Stage Summary:
- **أسس المرحلة 3 قائمة:** كائنان قانونيان (Swing §11.1، LiquidityZone §10.2) + 7 حمولات بنيوية/سيولية تخدم أنواع §20 الخمسة عشر عبر EVENT_PAYLOAD_MODELS وpayload_model_for — الكاشفان (3-b structure و3-c liquidity) يبنيان الآن حمولات من نماذج موثقة لا dicts يدوية، ويعملان مستقلين عن بعضهما (عقد import-linter محفوظ) فوق VolatilityState/ThresholdKey المشتركين.
- **قرارات موثقة خارج النص الحرفي (تمليكها للمنسق):** (1) ثلاثة مدققات فواصل إضافية بروح «الصخب في التحقق»: FvgEventPayload/OrderBlock gap_low/zone_low ≤ high، وPremiumDiscountEventPayload يشترط range_low < range_high صراحةً (النطاق المنحل قسمة على صفر في normalized_distance) بينما LiquidityZone يسمح بالمساواة (مستوى معزول منطقة صفرية العرض)؛ (2) التعدادات الجديدة العشرة سكنت وحدات مجالها (structure/liquidity) لا enums.py لأن enums.py مخصص حرفيًا للمنقول نصًا من الخطة وهذه قرارات موثقة المبرر — وكلها مصدَّرة من الواجهة الموحدة؛ (3) last_test_time إلزامي-قابل-للإعدام (نمط correlation_id) لا افتراضي None — صراحة الباني.
- **EQUAL_LEVEL_TOLERANCE (0.25×ATR) هو المفتاح الثامن** — سجلّا «المفاتيح السبعة» في docs/progress.md وADR-015 تاريخ صحيح للمرحلة 2 ولا يُحرَّف؛ توثيق المرحلة 3 القادم (المنسق) يذكر الثمانية.
- **ملاحظة للوكيل التالي (3-b/3-c):** الحمولات تحمل bar_time الشمعة المؤكِدة والبث بعدها حصرًا (§26.3/§27)؛ StructureBreakPayload مشتركة بين الأنواع الثلاثة فالتمييز في event_type بالمغلف لا في الحمولة؛ threshold(EQUAL_LEVEL_TOLERANCE) متاح فور الدمج بعد uv lock من الخيط الرئيسي.

---
Task ID: 3-e
Agent: Subagent (3-e — ترقية تغذية انحياز HTF البنيوية)
Task: المهمة 3-e — إغلاق ADR-016: توسيع HtfBiasInputs بحقول §9.2 البنيوية الاختيارية + مرشح خام بنيوي (_structural_candidate) بتوافق خلفي كامل مع وضع الوكيل (وضع الوكيل محفوظ حرفيًا عند غيابها).

Work Log:
- قراءة السياق الإلزامي كاملة: worklog (0→3-a وبخاصة 2-d موحيّد المحرك وADR-016 الواعد بهذه الترقية و3-a كائنات البنية)، §9.2 (انحياز HTF سياق لا مشغل)، §11.1 (Swing وقاعدة النظر الخلفي/تأخير التأكيد)، §11.4 (الإزاحة)، §26.3 (لا-نظرة-مستقبلية)، وكل الملفات المرجعية: htf_bias.py (عقود الوكيل كاملة)، regime.py وvolatility.py (نمط العقود والتحقق الصاخب وrange_expansion_percentile)، schemas/structure.py من 3-a، وtest_htf_bias.py (اختبارات الوكيل التي يجب أن تبقى خضراء بلا تعديل).
- توسيع HtfBiasInputs (frozen، توافق خلفي): 6 حقول اختيارية كلها None افتراضيًا — external_high_sequence/external_low_sequence (أسعار المتطرفات الخارجية المؤكدة زمنيًا تصاعديًا؛ تُستهلك confirmed-as-supplied بلا إعادة فحص تأكيد)، htf_displacement_direction ∈ {+1,-1,0}، expansion_state ∈ [0,1] (من VolatilityState.range_expansion_percentile)، dealing_range=(low,high) بشرط low ≤ high، close_price موجب. عقد التفعيل الموثق: الوضع البنيوي عند اكتمال التتابعين+الإزاحة+التوسع **جميعًا غير None** (الانتقاء بـ is not None لا بالصدق — الصفر حاضر)؛ أي غياب جزئي ⇒ وضع الوكيل حرفيًا (لا وضع هجين)؛ النطاق والإغلاق محسّنان لا يفعّلان النمط وحدهما ويطبقان معًا فقط.
- التحقق الصاخب الجديد (نمط الصخب في 2-d): إزاحة خارج {+1,0,-1}، توسع خارج [0,1]، نطاق معكوس/غير زوج/غير محدود، إغلاق وسعر متتابع غير موجب أو nan/inf — كلها ValueError عربية؛ التتابع الفارغ أو الأحادي جائز (بيانات غير كافية تُقرأ UNKNOWN لا تُرفض).
- HtfBiasConfig: حقلا إعداد إعداديان موثقان (ليسا توصية) يعملان في الوضع البنيوي وحده: contraction_threshold=0.3 (انكماش حصري الدنيا) وrange_position_split=0.5 (شطر موضع الإغلاق؛ (0, 0.5] — فوق النصف تتداخل منطقتا التناقض فيُرفض).
- المرشح البنيوي _structural_candidate بقواعد مرتبة الأولوية (موثقة في docstring): (1) تتابع <2 من أي جانب ⇒ UNKNOWN لهذا التحديث حصرًا (الحفظ الداخلي وقطع السلسلة بعقد النقص نفسه)؛ (2) اتجاه البنية من ذيلي التتابعين بتسمية صارمة — المساواة لا ترقّي إلى HH/HL ولا تحطّ إلى LH/LL بل تمتنع (أي تساوٍ ⇒ بنية غير موجّهة ⇒ NEUTRAL حتى مع LL بالمرآة)؛ (3) بنية غير موجّهة ⇒ NEUTRAL فلا ما بعدها يطبق؛ (4) إزاحة HTF مؤكدة معاكسة لاتجاه البنية ⇒ TRANSITION (نظير المنطقة الرمادية) **يعلو التهدئة والموضع عمدًا** (تعارض مؤكد أبلغ من إنكار إعدادي)؛ (5) انكماش (expansion < threshold) ⇒ NEUTRAL — بنية غير موسّعة لا تحسم اتجاهًا، والتوسع المتطرف لا يضيف شيئًا عمدًا (لا مكافأة توسع)؛ (6) موضع الإغلاق يناقض البنية ⇒ تخفيض إلى NEUTRAL فقط — position=(close−low)/(high−low) دونه يناقض الصاعدة وفوق 1−split يناقض الهابطة وبينهما محايد، وخارج النطاق يقع في منطقة التناقض تلقائيًا بلا قصّ، والنطاق المنحل (low==high) دليل غائب يُتجاهل؛ (7) الخريطة +1→BULLISH/−1→BEARISH.
- آلية 2-d كاملة (الدافئ/confirm_bars/transition_flips/TRANSITION يثبت) تعمل فوق المرشح البنيوي **دون تغيير سطر واحد** — التعديل الوحيد في update() هو استبدال سطر `raw = self._raw_candidate(inputs)` بجملة انتقاء الوضع (if/else)؛ والمستهلكون (HtfBiasState/snapshot.py/store.py) لم يُمسّوا.
- إعادة كتابة فقرة «قيود المرحلة 2» في رأس الموديول: المرحلة 3 وصلت وADR-016 أُغلق — الوضعان موثقان وسلوك الوكيل محفوظ حرفيًا؛ عقود الحتمية/لا-نظرة-المستقبلية موسعة للوضعين مع توثيق وراثة §26.3 عبر التغذية (confirmed-as-supplied)؛ «علاقة السيولة الكبرى» §9.2 موثقة خارج النطاق (طبقة الدمج فوق كاشف السيولة).
- اختبارات جديدة tests/unit/test_htf_bias_structural.py (73 اختبارًا، test_htf_bias.py بلا أي تعديل): انتقاء الوضع (توافق خلفي مقفول بمخرجات 2-d المعروفة، جزئية×4 تبقى وكيلًا بالاتجاهين، كاملة تنتصر البنية على وكيل مخالف، تبديل الوضع لكل تحديث، الصفر حاضر)، المرشح النقي (HH+HL/LH+LL/مختلط×2/تساوٍ×4/غير كافٍ×4 بحفظ داخلي)، الانكماش (حد 0.3 حصري، معايرة، لا مكافأة تطرف)، تناقض الإزاحة (الاتجاهان، موافقة/غياب، يعلو التهدئة والموضع معًا، البنية غير الموجهة تتجاهله)، موضع النطاق (تخفيض لا ترقية بالاتجاهين، المنتصف محايد، خارج النطاق، المنحل، لزوم النطاق والإغلاق معًا، معايرة الشطر 0.25)، الآلية فوق البنيوي (confirm=3، قطع السلسلة، تذبذب بنيوي ⇒ TRANSITION بمرآة اختبار 2-d، الدافئ، غير الكافي يقطع)، حتمية (repr مرتين) ولا-نظرة-مستقبلية (بادئة×4)، تحقق صاخب (17 رفضًا + الحدود الجائزة + فحص لا يعرف الأنماط)، الإعداد (افتراضيات + 6 رفضًا + حد النصف)، والتوثيق (ADR-016/الوضعان/proxy باقية/عقد التفعيل).
- إثبات تجريبي إضافي للتوافق الخلفي خارج الاختبارات: تشغيل نسخة HEAD مقابل المُرقّاة على 420 مدخل وكيل (400 عشوائية مثبتة البذر + 20 حالات خاصة) × 3 إعدادات — تطابق تتابعات الحالات بالتطابق التام (repr بايت-بايت).
- البوابات الحرفية: pytest الموجهة = 182 passed (50 وكيل + 73 بنيوية + 59 لقطة) · pytest الكامل = **1093 passed + 17 deselected** (خط الأساس 1020 بعد 3-a ⇒ +73 بلا انحدار ولا فشل عابر من الوكلاء الموازيين) · ruff check = All checks passed · ruff format --check = 8 files already formatted · mypy strict = Success في 96 ملفًا (يشمل ملفات 3-b غير الملتزمة الجارية — كلها خضراء) · lint-imports = 6 عقود محفوظة 0 مكسورة.
- الالتزام 1581664: ملفان فقط (htf_bias.py +297/−35 والاختبار الجديد 646 سطرًا) — uv.lock المشوّه مسبقًا وملفات 3-b غير المتعقبة وworklog لم تُلمس ولم تُلتزم (نطاق المهمة).

Stage Summary:
- **ADR-016 أُغلق فعليًا**: HtfBiasEngine صار يقبل تغذية §9.2 البنيوية الكاملة عبر حقول اختيارية معزولة — الوضع البنيوي يُنتقى لكل تحديث من اكتمال الأربعة المفعِّلة، ووضع الوكيل محفوظ حرفيًا (إثباتان: اختبارات 2-d بلا تعديل + مقارنة بايتية تجريبية ضد HEAD)؛ المستهلك (update/HtfBiasState/snapshot) لم يتغير أبدًا.
- **قرارات التصميم الموثقة**: (1) التسمية الصارمة بالمساواة تمتنع لا تحطّط — أي تساوٍ في ذيل أي جانب يجعل البنية غير موجّهة (NEUTRAL) حتى مع LL/HH في الجانب الآخر؛ (2) تناقض الإزاحة (TRANSITION) يعلو التهدئة الانكماشية ومخالفة الموضع (كلاهما NEUTRAL) — تعارض مؤكد بين دعويتين بنيويتين أبلغ من إنكار إعدادي؛ (3) قاعدة الموضع «تخفيض لا ترقية» بشطر واحد قابل للمعايرة range_position_split=0.5 (المنتصف محايد دومًا، وخارج النطاق يناقض تلقائيًا بلا قصّ، والنطاق المنحل دليل غائب)؛ (4) لا مكافأة للتوسع المتطرف عمدًا؛ (5) التتابع الفارغ/الأحادي بيانات غير كافية (UNKNOWN لهذا التحديث) لا خطأ تحقق.
- **للسيطرة verify_phase3 (3-f)**: لتغذية الوضع البنيوي عند كل شمعة HTF مغلقة — external_high/low_sequence = أسعار المتطرفات الخارجية المؤكدة (SwingScope.EXTERNAL من كاشف 3-b، بترتيب زمني تصاعدي، وبترشيح confirmation_time ≤ إقفال الشمعة الجارية — لا-نظرة-مستقبلية)، htf_displacement_direction = إشارة آخر إزاحة مؤكدة (+1 UP/−1 DOWN من BreakDirection، 0 إن لم تؤكد بعد)، expansion_state = VolatilityState.range_expansion_percentile نفس الشمعة، واختياريًا dealing_range من القمة/القاع الخارجيين الحاليين وclose_price إغلاق الشمعة؛ المحرك ينتقي الوضع ذاتيًا (حقول الوكيل يجوز أن تُترك كلها None في التغذية البنيوية)، والدافئ/التأكيد بسلوكهما المعروف.
- **حصيلة الاختبارات**: 73 جديدة (المجموع الكلي 1093 + 17 تكامل مؤجلًا) — المرحلة 3 توسع التغذية دون مساس المستهلك، كما وعد ADR-016 حرفيًا.

---
Task ID: 3-b (استكمال)
Agent: Main Agent (Z.ai Code — منسق المرحلة 3)
Task: استكمال المهمة 3-b بعد انقطاع وكيلها — إصلاح اختبارات القموم الخمسة الفاشلة + كتابة test_bos وtest_displacement وخصائص البنية

Work Log:
- الوكيل الأصلي قُطع (تجاوز مهلة الأداة) بعد كتابة كل مصادر structure (swings/bos/displacement/engine/events/_guards) وtest_swings فقط بـ5 اختبارات فاشلة.
- تتبع الإخفاقات: قناعان — (أ) شموع فاسدة في fixtures سابقة أصلحها الوكيل قبل انقطاعه جزئيًا، (ب) بقية متوقعات لم تطابق عقود المصدر الموثقة.
- كتابة test_bos.py (26 اختبارًا): fixtures §38.1 الحرفية — «BOS بخرق فتيلي فقط» (يُرفض افتراضيًا، يقبل مع wick_breaks_valid=True)، حد DISPLACEMENT_MIN بالضبط، near-miss تحت العتبة، تصنيف داخلي/خارجي، CHOCH كأول خرق معاكس بchoch_prior_direction والثاني المتتالي EXTERNAL_BOS، مقاييس محسوبة يدويًا.
- كتابة test_displacement.py (19): «إزاحة حقيقية» بالسمات الست الصحيحة، «توسع ضعيف» مرفوض، كل شرط مستقل مانع، قاعدة الركض الموثقة.
- كتابة tests/property/test_structure_properties.py (3 خصائص hypothesis): بادئة-لا-نظرة لكل قطع k، حتمية مزدوجة، تحجيم بقوى الأساسين (λ=2^k يبقي عديمات البُعد والتصنيفات والمعرفات بتّيًا).
- إصلاحات جودة لاحقة: RUF012 (ROWS صنوف → صفوف)، E501، RUF015، وتوقيعات _feed من list إلى Sequence.
- إصلاح mypy-ستة في test_bos: قارئتا `_direction`/`_highs` عبر دوال (إبطال تضييق mypy المثبَّت للخصائص عبر الاستدعاءات — مُثبت بتجربة مجس)، `_break_payloads` بتضييق isinstance عنصري، توقيع _payload_of معنون.
- الالتزام 46531e7 (مع 3-d).

Stage Summary:
- **structure مكتملة كاملة**: 6 موديولات + 68 اختبارًا وحدويًا و3 خصائص — العقود الموثقة في المصادر هي المرجع وكلها مختبرة حرفيًا.
- **درس mypy موثق للوكلا اللاحقين**: تضييق تعبيرات الأعضاء (is/len على الخصائص) يثبت عبر استدعاءات المحرك — القراءة عبر دالة تعيد النوع المعلن المفتوح.

---
Task ID: 3-d (استكمال)
Agent: Main Agent (Z.ai Code — منسق المرحلة 3)
Task: استكمال المهمة 3-d بعد انقطاع وكيلها — إصلاح اختبارات الأهداف الثلاثة + كتابة خصائص السيولة الناقصة + توحيد عقد التغذية الاختياري

Work Log:
- الوكيل الأصلي قُطع بعد كتابة كل مصادر liquidity (zones/sweep/targets/engine) وثلاثة ملفات اختبارات، وبقي test_targets بثلاثة إخفاقات وخصائص السيولة غير مكتوبة.
- إصلاح test_targets: (1+2) fixtures معكوسة ناقضت العقد الموثق «المساواة عند الحافة مشمولة والتجاوز الصارم مستبعد» — صُححت المنطقة المجتازة لتصبح دون السعر بفارق ضئيل؛ (3) فهارس شموع مكررة في حلقة الواجهة — رقيت بenumerate.
- كتابة tests/property/test_liquidity_properties.py (5 خصائص hypothesis): بادئة-لا-نظرة (أحداث+مناطق)، حتمية، تحجيم بقوى الأساسين عبر كامل الواجهة، قراءة أهداف محفوظة التحجيم (مسافات معيارية وصلات محفوظة وفواصل محججة)، حدود الدرجات الثلاث ∈ [0,1].
- تشخيص تعليق hypothesis (SIGKILL بعد دقيقتين): كان تقليصًا لمثال فاشل — كشفه مجس حتمي: **خطأ في اختباري أنا** (تحجيم مزدوج λ² في مشتق المتطرفات) لا في المحرك — المحرك حجّج كل مدخلاته الصحيحة بدقة بتّية (مناطق الجلسة عند 4×بالضبط).
- توحيد عقد التغذية: معامل vol في LiquidityEngine/LiquidityMapEngine/SweepDetector.update أصبح `VolatilityState | None` (مطابقة عقد حزمة البنية) — أول شمعة عند محرك التقلب الموازي تعيد None فتُعامل كغياب ATR: لا عتبات ولا نوافذ اجتياح، مع تعديل الطرق الداخلية الموافقة.
- إصلاحات ruff/mypy المتفرقة + الالتزام 46531e7 (مع 3-b).

Stage Summary:
- **liquidity مكتملة كاملة**: 4 موديولات + 122 اختبارًا وحدويًا و5 خصائص.
- **العقد الموحد للكاشفين**: `update(candle, vol: VolatilityState | None, new_swings)` — لا قيمة افتراضية مزيفة لغياب الحالة، غياب معلن يمر كما هو.
- **معرفات المناطق بلا أسعار** (uuid5 بروح D-07) — ثبات الهوية تحت التحجيم مثبت بالخصائص.
- المجموع بعد الاستكمالين: **1308 اختبارات خضراء** + mypy strict + 6 عقود استيراد.

---
Task ID: 3-c (استكمال)
Agent: Main Agent (Z.ai Code — منسق المرحلة 3)
Task: استكمال المهمة 3-c بعد انقطاع وكيلها — كتب المصادر الثلاثة (fvg/order_blocks/premium_discount) وتوصيل الواجهة ومد مقارن التحجيم ثم انقطع قبل اختبارات الوحدات والالتزام

Work Log:
- الوكيل كتب المصادر الثلاثة بتوثيق عقود كامل قبل انقطاعه: fvg.py (362 سطرًا)، order_blocks.py، premium_discount.py + توسيع اتحاد EmittedEvent وتوصيل StructureEngine بمكوناته الستة ومد خصائص التحجيم للحمولات الثلاث.
- تشخيص تعليق خصائص البنية (SIGKILL بتقليص hypothesis): مجس حتمي بمسار عنيف كشف **خلل أبعاد جذريًا في بوابة الإزاحة** (من 3-b): كانت تقارن atr_multiple عديم البُعد بعتبة DISPLACEMENT_MIN السعرية (atr×المعامل) — عند ATR كبير ترفض الاندفاع الصحيح وعند صغير تقبل الضعيف؛ نجت اختبارات الوحدة لأنها عند ATR=1.0 حيث يتطابق القياسان. الإصلاح: مقارنة سعرية price_range ≥ threshold — أُثبت بالمجس (λ=4 وλ=0.25 متطابقان بعدها) وبخصائص التحجيم.
- كتابة tests/unit/test_fvg.py (21 اختبارًا): الكشف القطعي بالفاصلين والاستحالة البرهانية، آلة الحالة كاملة (بقاء أبدي/تلطيف جزئي بتوقيت أول/ملء باجتياح دون إغلاق/إبطال من أي حالة)، رتابة fill_fraction المقصوصة، بث واحد لا يكرر، غياب ATR يمنع التكوين والفجوة الضائعة لا تعود والملء يستمر بلا ATR، حتمية المعرفات، الحوارس الأربعة.
- كتابة tests/unit/test_order_blocks.py (20): المصدر المفرد/العنقود المتراص بفاصل يتجاوز التسامح مستبعد، الديدجة توقف التتبع، البث المؤجل (كسر معاكس لا يحقق/النافذة تنقضي فتدرد/الكسر بشمعة الإزاحة نفسها يحقق فورًا)، التسمية تتبع الإزاحة (DOWN→BEARISH)، حلقات الاختبار (المتتالي حلقة/الفاصل يفتح ثانية/شمعة البث ليست اختبارًا)، صيغة الرفض والقص السالب، حدود الجودة، حتمية، والرفض الصاخب الأربعة (تغذية غير متسقة/نوع غريب/طابع لا يطابق/هوية غريبة).
- كتابة tests/unit/test_premium_discount.py (16): الرفض الملتبس (لا نطاق بلا خارجيين/الداخلية تهمل/الطرف المعلق يتتبع والحساب وحده يعلق)، المتساويات الصارمة والمنصف NEUTRAL لا يُبث، جدول الانتقالات (أول تحديد يبث/العبور يبث/البقاء لا/العودة عبر محايد لا)، الإقصاء يتجاوز ±1 عبر انتقال فعلي، الامتداد الأحادي (السقف لا ينقص والأرضية لا ترتفع) وإعادة تقييم الشمعة نفسها، حتمية، حوارس.
- إصلاحات جودة شاملة (ruff format/check + mypy strict حتى 116 ملفًا نظيفة).

Stage Summary:
- **كواشف §11 مكتملة بالكامل**: ستة مكونات في StructureEngine (قمم/كسور/إزاحة/فجوات/كتل/موقع) — 1365 اختبارًا خضراء.
- **أهم درس في المرحلة**: خاصية التحجيم ليست ترفًا — كشفت خلل أبعاد نجت منه كل اختبارات الوحدة (تطابق القياسين عند ATR=1.0). كل مقارنة عتبة يجب أن تكون سعرًا بسعر أو نسبة بنسبة، أبدًا لا مختلطة.
- **لـ3-f**: EmittedEvent أضحى اتحادًا من خمس حمولات؛ premium/discount لا يقبل معامل تقلب أصلًا (رياضيات موقعية صرفة)؛ displacement_event_id صيغة uuid5 معلنة للربط.

---
Task ID: 3-f
Agent: Main Agent (Z.ai Code — منسق المرحلة 3)
Task: بوابة المرحلة 3 — هجرة 0004 + مخازن التحليلات + ناشر أحداث NATS + verify_phase3 + التوثيق والإغلاق

Work Log:
- هجرة 0004_phase3_analysis_tables: الجداول الثلاثة §31.3 (structure_events بفهرسيه، liquidity_zones بحالة دورة الحياة وقيد importance ∈ [0,1]، pattern_events) — صعود/هبوط أخضران عبر اختبارات التكامل بعد تحديث تدبيس الرأس المتقادم إلى النمط الديناميكي (قرار ADR-019 نفسه).
- بنية علوية موحدة للمخازن: AnalysisEventStore في structure (upsert_event بمسار pydantic صاخب + upsert_swing بسجل SWING_CONFIRMED + recent_events/recent_swings/count) وLiquidityZoneStore في liquidity (upsert_zone بدورة الحياة + قراءات round-trip) — asyncpg على اتصال المستدعي بنمط 2-f.
- ناشر أحداث التحليل في worker: build_envelope (مصنع نقي — event_id حتمي روح D-07 وreceive_time إلزامي من المستدعي) + AnalysisEventPublisher (مواضيع market.event.{instrument}.{tf}.{type-lowercase} برؤوس §32) + عرض إقلاعي جديد في __main__ بجانب عرض اللقطة.
- سكربت البوابة scripts/verify_phase3.py (10 فحوص صارمة): العينة الثلاثية الأطر نفسها، المسار الكامل (بنية لكل إطار + سيولة 1م بمتطرفاتها عند شمعة تأكيدها + انحياز 1h بالوضع البنيوي)، الحتمية (هاش مسارين)، لا-نظرة-مستقبلية (بادئة 1415)، التحجيم (λ=2)، القانونية (مغلف §32 + مخطط الحمولة لكل حدث)، الاكتفاء، ثم الحي: NATS بالتحقق والقاعدة بإرسال مزدوج وقراءة round-trip.
- إصلاحات أثناء البوابة: (1) تسلسل JSON الكامل للحمولات في فحص القانونية (التواريخ كائنات Python لا سلاسل ISO)؛ (2) مخزن الأحداث يمرر الحمولة عبر نموذجها ثم model_dump_json (تحقق صاخب عند الكتابة)؛ (3) مفتاح متطرف التخزين يشمل swing_id — التصادم عند تأكيد قطبيتين بشمعة واحدة كان يسقط إحداهما؛ (4) **خلل ترتيب في مسار البوابة**: حلقة تسجيل المتطرفات كانت تسبق تغذية السيولة فتحرمها من متطرفاتها (19 منطقة بدل 402) — التغذية أولًا بمساعد موحد؛ (5) مقارنة المناطق بالمعرف لا بالموضع (ترتيب SQL بمعرفها ليس ترتيب الإنشاء)؛ (6) تنظيف مسبق لصفوف الأداة — البوابة قابلة للتكرار على قاعدة عاشت تشغيلات سابقة.
- اختبارات وحدات الناشر (8: حتمية المعرف عبر الاستدعاءات، اختلافه بين الأحداث، اكتمال الحقول التسعة، مخطط المغلف المصدَّر، الموضوع، البث بالعميل الوهمي، النمطي lowercase، إلزامية receive_time).
- توثيق الإغلاق: progress.md (جدول المرحلة 3 كاملًا + البوابة) وdecisions.md (ADR-020 خلل الأبعاد ودرس خاصية التحجيم، ADR-021 قرارات التخزين) — منسوخان إلى engine/docs.

Stage Summary:
- **بوابة المرحلة 3 مغلقة رسميًا**: `make verify-phase3` — الحتمية (458294d480be1afc…) + لا-نظرة (بادئة 1415 مستقلة) + التحجيم (λ=2 محفوظ الأنواع والتصنيفات) + القانونية (856 حدثًا/11 نوعًا بمخططاتها) + الاكتفاء (366 متطرفًا/402 منطقة/انحياز بنيوي معلوم) + NATS حي + قاعدة idempotent بround-trip.
- **حصيلة المرحلة 3**: 433 اختبارًا جديدًا (940→1373) عبر 6 مهام كواشف + بوابة؛ حزمتا structure (6 مكونات) وliquidity (4) مكملتان فوق أسس schemas الموحدة؛ هجرة 0004؛ ناشر أحداث بمغلفات حتمية.
- **أهم درسين للمراحل القادمة**: (1) خاصية التحجيم فاحص الأبعاد الأول (ADR-020) — تُفرض على كل كاشف جديد قبل اعتماده؛ (2) ترتيب التغذية داخل حلقة المسار جزء من عقد الصحة — التسجيل لا يسبق الاستهلاك.
- **التالي**: المرحلة 4 — التدفق والفوتبرنت (§12): footprint من aggTrades بbuyer-is-maker، مقاييس الشريط، امتصاص/إنهاك، جهد مقابل نتيجة.

---
Task ID: R-2 (مزامنة الاسترداد + تدقيق التقدم)
Agent: Main Agent (Z.ai Code — Coordinator)
Task: طلب المالك: التحقق من التقدم بحسب الخطة وتحديد المرحلة التالية + المزامنة مع GitHub

Work Log:
- تشخيص التراجع المحلي: النسخة المحلية للبيئة عادت إلى لقطة نهاية المرحلة 1 (main عند cd4f535 بلا remote) بينما المستودع البعيد يتقدم حتى بوابة المرحلة 3 (fddd713) — البعيد هو مصدر الحقيقة.
- مقارنة تحفظية قبل المزامنة: نقطة تفتيش المنصة cd4f535 المحلية نظيرها الملتزم على البعيد (b8a4a29 — نفس الرسالة UUID والمؤلف والتاريخ والمحتوى) فلا فاقد؛ الأوساخ العاملة الوحيدة (dev.pid وarrival-log) ملفات تشغيل.
- المزامنة: إضافة remote origin (توكن المالك) → fetch → reset --hard origin/main (fddd713) — المحلي الآن يحمل المراحل 0–3 كاملة.
- استرداد البيئة وفق بروتوكول R-1: uv sync --all-packages (venv أعيد بناؤه كاملاً) + .env من المثال بسرّ engine-secret المتوائم مع افتراض supervisor (هذه المرة data/ محت بالكامل فأعيد إنشاء s3-config.json تلقائياً عند الإقلاع) + make infra-provision (nats 15M + postgres Zonky + seaweedfs 4.48/213M عبر Bearer المصلح في cc6949c).
- إطلاق الأغلفة double-fork (ADR-002): engine-infra (supervisor: postgres/nats/seaweedfs/migrate/worker كلها ✓) وengine-api (uvicorn :4001 healthz 200).
- إعادة إثبات البوابات الثلاث على البيئة المستردة: make gate = 1373 passed (ruff+mypy strict+import-linter+pytest) · pytest -m integration = 17 (16 passed + 1 skipped بحكم تحصين fddd713 للشبكة المقيدة) · alembic عند 0004_phase3_analysis_tables (head) · make verify-phase2 = خضراء كاملة (حتمية + لا-نظرة + عتبات تطبيعية + NATS + قاعدة idempotent) · make verify-phase3 = خضراء كاملة (حتمية 458294d480be1afc… + 856 حدثاً عبر 11 نوعاً قانونية + تحجيم λ=2 + NATS + قاعدة).

Stage Summary:
- **لا فاقد إطلاقاً:** كل عمل المرحلتين 2 و3 كان ملتزماً ومرفوعاً على GitHub — الاسترداد كان مزامنة استرجاع لا إعادة بناء.
- **الحالة بحسب الخطة:** المراحل 0 و1 و2 و3 مكتملة ببواباتها المغلقة وموثقة في progress.md (ADR-001..021) — **التالي: المرحلة 4 (التدفق والـfootprint) بحسب build_plan §D**.
- **درس مؤكد:** أي تراجع للقطة المحلية يُسترد بالمزامنة من البعيد أولاً ثم بروتوكول R-1 للبيئة — الرفع المنتظم بعد كل مرحلة هو صمام الأمان الفعلي.

---
Task ID: 4-a
Agent: Main Agent (Z.ai Code — Coordinator)
Task: أسس المرحلة 4 — حمولات أحداث التدفق + العتبات + المرجع الذهبي + عينة المرحلة 4

Work Log:
- قراءة §12 كاملاً (739-825) + §8.2 (FootprintBar) + §20 (صفوف التدفق: ABSORPTION_BUY/SELL وFLOW_CONTINUATION_UP/DOWN وEXHAUSTION_UP/DOWN وBUY/SELL_IMBALANCE_CLUSTER بأوزانها) + §31.2 (footprint_bars/rows) + §38.1 (fixtures الامتصاص) + بنية المرحلة 3 (envelope/structure/events/store/verify_phase3) وعقود import-linter (orderflow في طبقة الكواشف فوق market_state/ingestion).
- schemas/orderflow.py: وحدة كاملة — FlowDirection (UP/DOWN) وAbsorbedPressure (BUY/SELL — ABSORPTION_BUY⇒الضغط البيعي امتُص حرفي §20) وImbalanceSide + AbsorptionConditions (الشروط الأربعة §12.3 حرفيًا: elevated_delta/limited_extension/repeated_response/opposite_disployment اختياري None) + 4 حمولات: AbsorptionEventPayload (delta/delta_share/excursion_atr/conditions/zone_id/confirmed=False مرشح §12.2) وFlowContinuationEventPayload (delta/delta_share/response_atr/efficiency) وExhaustionEventPayload (efficiency/efficiency_prev/decay_ratio/failed_extremes/follow_through §12.4) وImbalanceClusterEventPayload (bar_count≥1/total_imbalances/max_row_ratio/aligned_with_displacement §12.6) — كلها مجمّدة extra=forbid بوسم المصدر الموثق (§12.7) في الترويسة.
- تسجيل الثمانية في EVENT_PAYLOAD_MODELS (envelope.py) وتوسيع صادرات __init__ (8 أسماء بترتيبها الأبجدي) وexport.py (ALL_MODELS + MODEL_PLAN_REFS: §12.2/§12.3/§12.4/§12.6) — 29 مخططًا مُصدَّرة idempotent بايت-بايت.
- ThresholdKey مفتاحان جديدان بمعاملين افتراضيين 0.5: ABSORPTION_EXTENSION_MAX (§12.3 شرط 2 — «امتداد محدود» نسبة للعدوان) وFLOW_RESPONSE_MIN (§12.2 — «استجابة قوية» لاتفاق الجهد والنتيجة) — اختبارات التغطية والخطية الموجودة تمتد تلقائيًا.
- KlineBar توسعة موثقة (الوعد المعلق في docstring): taker_buy_volume (index 9 — المرجع الذهبي لحجم الشراء العدواني: buyer_is_maker=False ⇒ مشترٍ متسبب) وtrade_count (index 8) — التوافق الخلفي مثبت (صفوف الاختبارات الافتراضية تحمل الفهرسين).
- scripts/fetch_phase4_fixture.py + التقاط فعلي: نافذة 120 دقيقة BTCUSDT (30 ساعة خلفًا، محاذاة حد الدقيقة): 35,932 صفقة aggTrades → trades.parquet 680KB حتمي + 120 شمعة 1m مرجعية بـtaker_buy_volume → tests/fixtures/phase4/.
- **إثبات المرجع الذهبي فورًا**: مجموع كميات buyer_is_maker=False عبر النافذة = 1640.4220 == takerBuyBaseAssetVolume للبورصة (فرق 0.000000) — «المطابقة الإحصائية» لبوة المرحلة 4 قابلة للتحقق الدلو-بالدلو. ملاحظة موثقة: عدّاد klines يعدّ الصفقات الفردية بينما aggTrades مجمّعة — فالمرجع الحجمي هو الذهبي، والعدّاد استرشادي.
- PositiveInt أضيف إلى _types.py (إضافة تراكمية) لعنقيد لا يصح بصفر أشرطة.
- اختبارات: tests/unit/test_schemas_orderflow.py — 38 اختبارًا (round-trip/جمود/حقول غريبة لكل الخمسة + الحدود §12 + التطابق الاتجاهي ABSORPTION_BUY⇒SELL + المرشحية confirmed=False + التسجيل الثماني في الخريطة) + تحديث اختبارَي سجل المرحلة 3 للتوسعة المشروعة (15 بنيوية حصرًا → 15+8=23 مع فصل المجموعتين صراحة).
- تصحيحات بوابة: ruff format للسكربت وE501 وraw-string للمطابقة النمطية و6 إصلاحات آلية.
- البوابة: make gate = 1411 passed (+38) وschemas check = 29 مخططًا idempotent.

Stage Summary:
- **أسس المرحلة 4 مكتملة ومثبتة**: عقود حمولات التدفق الثمانية موثقة ومصدَّرة ومسجلة في مغلف §32، وعتبتا التدفق التطبيعيتان (atr×0.5) في قاموس ThresholdKey الموحد، والمرجع الذهبي (taker_buy) ملتقط في عينة 120 دقيقة حقيقية مع إثبات تطابق تام.
- **عقد الواجهة للكواشف اللاحقين**: الكواشف تستهلك schemas.FootprintBar (+Candle+VolatilityState) وتخرج سجلات EmittedEvent الخاصة بها على نمط structure/events.py — لا تعتمد على بنّاء الفوتبرنت الداخلي (توازٍ آمن بين 4-b/4-c/4-d).
- **التالي**: 4-b بنّاء الفوتبرنت (ذهبي دلو-بدلو ضد klines) بالتوازي مع 4-c (مقاييس وعناقيد) و4-d (امتصاص/إنهاك/جهد-نتيجة).

---
Task ID: 4-b
Agent: footprint-builder (full-stack-developer)
Task: المهمة 4.1 (4-b) — بنّاء الفوتبرنت الحدثي من aggTrades بمنهجية الطرف المتسبب: `orderflow/footprint.py` + `tests/unit/test_footprint.py`

Work Log:
- قراءة السياق الإلزامي كاملة: worklog (تركيز 4-a وR-2 وإدخالات المرحلة 3 — نمط «الاستكمال بعد انقطاع» مألوف)، Master Plan §8.2 (سطور 414-441) و§12 كاملًا (12.1/12.5/12.6/12.7) و§26.3 و§27، وكل المرجع: rows.py (عقد الواجهة المجمد — لم يُمس)، events.py، market.py (حدود FootprintBar)، candles.py (عقد CandleBuilder/bucket_floor/QUALITY_SEVERITY_LADDER حرفيًا)، test_candles.py (نمط الاختبارات)، fixtures/phase4 (35,932 صفقة + 120 kline + manifest)، test_schemas_models.py (make_footprint).
- وجدت عمل جلسة 4-b سابقة مقطوعة غير ملتزمة (footprint.py + test_footprint.py بلا إدخال worklog وبلا التزام) — لم أثق بها: مراجعة سطر-بسطر ضد عقد المهمة، ثم إعادة تحقق يدوي من كل قيم الذهبي: الشريط 1 (8 صفوف: buy=37/sell=23/total=60/delta=+14، POC=104 فريد 24، منطقة قيمة غير متناظرة [102..104] بفوز الثنائية الدنيا 20 على العليا 10، عدادات 2/2، صفوف الدلتا القصوى 104(+16)/102(−6)) والشريط 2 (تعادل الثنائيتين 8=8 حُسم بقاعدة الجهة المضادة لميل POC: منتصف المغطى 202 < POC 203 ⇒ الدنيا ⇒ val=199/vah=203) والشريط الأحادي المترهل بالإقفال الصريح.
- **تحقق مستقل من أثر الحدود في الذهبي الحقيقي** (سكربت تجميع قائم بذاته لا يمس البنّاء): buy_volume (taker) مطابق **تمامًا في كل الدلاء 120/120**؛ total يختلف في دلوي 20:28 (+0.150) و20:29 (−0.150) فقط ومجموعهما صفر — الصفقة المجمّعة عند 20:28:59.994 (كمية 2.734 بيعية عند 84591.6) تعبئاتها الفردية امتدت عبر الحد فقاسها محرك klines لدى البورصة مشطورة بينما aggTrades يحملها كلها بطابع 20:28:59.994 — أثر بيعي فحسب فالمرجع الشرائي سليم. القيم الموثقة `_BOUNDARY_TOTAL_DELTA` خاصية بيانات حقيقية لا مسكنة اختبار.
- أضفت الناقص الوحيد من عقد المهمة: `closed_bars() -> tuple[FootprintBar, ...]` (قراءة صرفة فوق closed_bars_with_rows بنفس الترتيب الحتمي) + توثيقها في docstring الصنف + تأكيدات ذهبية عليها.
- القرارات الموثقة في رأس footprint.py (مراجع § في كل عقد): تعادل POC ⇒ الأقرب لـVWAP ثم الأدنى سعرًا (وتعذّر VWAP في المتحنة ⇒ الأدنى)؛ منطقة القيمة 70% توسّع ثنائي من POC (الأكبر حجمًا يفوز، الجهة المنفدة تتوحدها، التعادل ⇒ الجهة المضادة لميل POC داخل النطاق المغطى والتساوي التام ⇒ العليا، تجاوز الهدف بثنائية كاملة جائز)؛ صفوف الدلتا القصوى بإشارة صارمة وتعادلها ⇒ الأدنى سعرًا وNone عند الانعدام؛ الدلو الفارغ لا يُبنى (الفجوات تتخطى) والسعر صفر الكمية له صف يُعدّ؛ المتحنة shares=0.0 وvah=val=poc؛ source_feed آخر مغذٍ يفوز + عدّاد feed_id_conflicts (لا حقل قانونيًا له في §8.2 المغلق)؛ رفض buyer_is_maker=None يسبق التصنيف الزمني (متأخر بلا علم يُرفض لا يُحصى)؛ عقد إرجاع add_trade = CandleBuilder حرفيًا (None عند البدء/التأخر، المقفل عند العبور، المتطور داخل الدلو) — فُضِّل على قراءة بديلة لصياغة المهمة لأنها المصرح بها «حرفيًا» ولأن بوابة اللا-نظر بايت-ببايت تقتضيها.
- البوابات: ruff format + ruff check على نطاقي نظيفان؛ mypy strict (الأمر القانوني) = Success في 135 ملفًا؛ **pytest الكامل = 1723 passed + 17 deselected بلا أي فشل** (لا انحدار)؛ lint-imports = 6 عقود محفوظة (استيراد ingestion.candles من orderflow قانوني بعقد الطبقات). بوابة `make gate` الكاملة تعثرت **حصريًا** في ruff format لثلاثة ملفات من الوكيل الموازي 4-d (absorption.py/exhaustion.py/test_effort_result.py — لم تُلمس منذ 01:15-01:19) — أعدت المحاولة ثلاثًا عبر أكثر من 5 دقائق ثم طبقت بروتوكول التحذير التوازي: إثبات نظافة نطاقي منفردًا + الالتزام بملفاي فقط.
- الالتزام c041728: ملفان فقط (footprint.py 603 سطرًا + test_footprint.py 1087 سطرًا، 1686 إدراجًا) — لا git add -A؛ ملفات الوكلاء الموازيين وpyproject.toml/__init__.py المشتركة بقيت غير ملتزمة.

Stage Summary:
- **المنتج:** FootprintBuilder — بنّاء حدثي صرف لكل (instrument_id) بإطار إلزامي صريح من البادئة، يصنف كل صفقة بعدوانية طرفها المتسبب (buyer_is_maker=False ⇒ شراء، True ⇒ بيع) في صفوف سعرية تصاعدية، ويشتق مقاييس §8.2 كاملة عند كل إصدار (متطور ومقفل): المجاميع/الدلتا/الحصص/POC/VAH-VAL بمنطقة 70%/عدادات الاختلال الصفّي/صفوف الدلتا القصوى/الجودة بسلّل الشدة/وسم المصدر والمنهجية §12.7 — بعقود §27 (المتطور لا يفوّظ، المقفل جمود، المتأخرون يحصون) و§26.3 (لا-نظرة-مستقبلية).
- **الاختبارات:** 170 في test_footprint.py تغطي بنود المهمة التسعة: ذهبي يدوي بثلاثة أشرطة (توسّع ثنائي غير متناظر + تعادل محسوم + مترهل أحادي)، ذهبي حقيقي 120 معاملًا (buy == taker_buy بـrel=1e-9 في كل الدلاء، total/sell == المرجع في 118 + أثر حدود ±0.15 موثق ومحصور في دلويين)، حتمية sha256، لا-نظرة بايت-ببايت + خاصية derandomize، متأخرون، جودة، اختلال صفّي (10/2 و1/9 و4/4 + معامل البادئ)، رفض None، وخصائص (حصص تسجم 1، |delta|≤total، صفوف تصاعدية، POC∈[VAL,VAH]، VAH≥VAL، الشريط==صفوفه).
- **للوكيل 4-c:** مدخلك `closed_bars_with_rows()` (صفوف تصاعدية حصرًا بعقد rows.py) و`evolving(instrument_id)` قراءة حية لا تُعدّ تحديثًا؛ ملاحظة: قاعدة تعادل POC في `_orderflow_fixtures.py` (الأدنى سعرًا) تخالف قاعدة البنّاء (الأقرب لـVWAP) — لا مشكلة لبناء أشرطة اصطناعية اعتباطية، لكن لمحاكاة مخرجات البنّاء فعلًا استخدم قاعدته.
- **للمنسق/4-d:** (1) pyproject.toml غير الملتزم يحمل تبعية engine-ingestion التي يحتاجها footprint.py — يجب أن تُلتزم مع دمج المرحلة؛ (2) ملفات 4-d الثلاثة تحتاج `ruff format` قبل اخضرار البوابة الكاملة؛ (3) لم أضف FootprintBuilder إلى __init__.py الحزمة (ملف مشترك قيد تحرير الوكلاء الموازيين، والاصطلاح القائم — ingestion لا يصدّر CandleBuilder من الجذر — استيراد الوحدة الفرعية مباشرة).

---
Task ID: 4-c
Agent: flow-metrics-builder (full-stack-developer) — أُتمم التسليم بيد المنسق بعد انقطاع أمد الوكيل
Task: المهمة 4.2 (جزء المقاييس والاختلالات) — المقاييس المتتالية وعناقيد الاختلال الصفّي (§12.1+§12.6)

Work Log:
- (الوكيل المنقطع أنجز كامل التطبيق والاختبارات قبل انقطاعه؛ المنسق تحقق منها وأتمم الالتزام والتوثيق.)
- metrics.py: دوال صرفة على متتاليات FootprintBar — delta_trend (ميل انحدار دلت الأشرطة) وvolume_concentration (من Bar وحده) وvolume_concentration_rows (حصة منطقة القيمة من الإجمالي عبر الصفوف — أصدق تمثيل).
- imbalance.py: ImbalanceClusterDetector كاشف حالة موضعية — ImbalanceClusterConfig (min_imbalance_count/min_cluster_bars/ratio_min) + حقن displacement_aligner؛ إعلان العنقيد عند آخر شريط فيه حصرًا (لا-نظرة)، السلسلة المعاكسة تكسر، لا إعادة بث للنفس الأشرطة (حتمية بلا رفرفة).
- _orderflow_fixtures.py: بناة أشرطة فوتبرنت اصطناعية مشتقة الحقول من صفوفها (عدادات الاختلال من rows.py نفسها).
- الاختبارات: 78 في test_imbalance_clusters.py وtest_flow_metrics.py — عنقيد كامل/تحت الحد/انكسار الجهة/لا-نظرة/حتمية/الحقن وخصائص hypothesis بذر مثبت.
- صادرات __init__.py حُدثت (SATURATED_ROW_RATIO وImbalanceClusterConfig/Detector وdelta_trend وvolume_concentration*).

Stage Summary:
- **عناقيد الاختلال §12.6 مكتملة**: الرصد الخام (العدادات) والأهمية السياقية (aligned_with_displacement عبر الحقن) معًا في حمولة 4-a القانونية — «اختلال معزول وزن منخفض؛ متكرر متوائم مع الإزاحة يحمل دليلًا أكثر».
- **قرار موثق**: التركّز له مساران — من FootprintBar وحده (قابل للتشغيل بلا صفوف) ومن BarRows (حصة منطقة القيمة 70%).

---
Task ID: 4-d
Agent: flow-detectors-builder (full-stack-developer) — أُتمم التسليم بيد المنسق بعد انقطاع أمد الوكيل
Task: المهمتان 4.3+4.4 — الامتصاص (§12.3) والإنهاك (§12.4) ومصفوفة الجهد مقابل النتيجة (§12.2)

Work Log:
- (الوكيل المنقطع أنجز effort.py وabsorption.py وexhaustion.py وtest_effort_result.py قبل انقطاعه؛ المنسق تحقق من الاكتمال والكيفية ثم كتب اختبارَي absorption/exhaustion الناقصين وأتمم الالتزام والتوثيق.)
- effort.py: EffortResultState (المصفوفة الأربع +INSUFFICIENT_VOLATILITY) وclassify_effort_vs_result (عتبة الاستجابة FLOW_RESPONSE_MIN تطبيعية حصرًا) وefficiency الدالة الصرفة (استجابة/atr ÷ |حصة|) وusable_atr/bar_delta_share/directional_response/check_flow_inputs وFlowGuards (هوية الزوج + ترتيب تصاعدي قطعي + ثنائية متطابقة + لا حالة تقلب من المستقبل).
- absorption.py: الشروط الثلاثة الإلزامية + الرابع المحقون — عداءا فشل مواصلة اتجاهيان (الشريط الصغير يفشل بالاتجاهين)، الامتداد السالب يجتاز «المحدودية» (أبلغ عدم توافق) لكن إيجابية الحمولة تمنع البث (الحالة تبقى مسلحة)، قفل عدم التكرار لكل جهة حتى انكسار الشرط 1 ثم عودته، لا مرشح بلا تقلب.
- exhaustion.py: نوافذ مستقلة لكل اتجاه (كفاءات أشرطة الجهد في الاتجاه وحدها)، نصفان متساويان (window زوجي)، القمم/القيعان الفاشلة مقارنة سعرية صرفة ضد نافذة خلفية مكتملة، علامات المواصلة لا تحتسب بلا عتبة تطبيعية (غياب دليل لا دليل)، الإعلان قياس لا توصية.
- اختبارات المنسق المكملة: test_absorption.py (16) — المرشح الكامل ABSORPTION_BUY بabsorbed_pressure=SELL وconfirmed=False والمرآة وكل شرط مانع مستقلًا وإيجابية الامتداد (المسلح يبث لاحقًا) والقفل/الفك والجهتان مستقلتين والحقن والحتمية واللا-نظرة والتحجيج λ=2 (atr مضاعف مع امتداد مضاعف ⇒ نفس excursion_atr) وتحقق الإعداد؛ test_exhaustion.py (13) — السناريو الكامل بحساب يدوي للكفاءات (9.8 عالية بمشاركة صغيرة و0.4 منهارة بمشاركة كبيرة) وقيم الحمولة الدقيقة وكل عنصر مانع مستقلًا والمرآة الهابطة والحتمية واللا-نظاعة وتحقص الإعداد.
- pyproject: تبعيتا engine-ingestion (bucket_floor وread_parquet للبنّاء) وengine-market-state (VolatilityState/ThresholdKey للكواشف) أضيفتا لحزمة orderflow.
- البوابة بعد التكملة: make gate = 1752 passed (ruff+mypy strict+import-linter+pytest) — أخضر كاملًا.

Stage Summary:
- **مصفوفة الجهد/النتيجة بتغطية كاملة مختبرة** (خاصية اكتمال حصرية) — «الجهد والنتيجة يُقارنان عند فاصل تطبيعي واحد»؛ FLOW_CONTINUATION حدث توافق مباشر عبر كواشف الدمج اللاحقة.
- **الامتصاص مرشح قابل للتأكيد**: confirmed=False عند الإنشاء دوماً — التأكيد اللاحق (شرط 4 المحقون) يرفع درجة المرشح نفسه؛ zone_resolver يوصل بمناطق السيولة في بوابة 4-f.
- **الإنهاك نوافذ اتجاهية مستقلة**: «امتداد متناقص لكل وحدة حجم» و«كفاءة دلتا متدهورة» القياس نفسه (نص الخطة يجعلهما كذلك) — والبث لكل شريط مستوفٍ قياسًا خامًا (التباعد مسؤولية الدمج §19).
- **التالي (4-e)**: هجرة 0005 (footprint_bars/rows §31.2) + المخزن + توصيل الناشر في worker.

---
Task ID: 4-e
Agent: Main Agent (Z.ai Code — Coordinator)
Task: بنية تحتية للتدفق — هجرة 0005 + مخزن + توصيل البث في worker (§31.2/§31.3)

Work Log:
- قراءة §31.2/§31.3 (جداول الفوتبرنت والأحداث التدفقية) وأنماط 0003/0004 ومخازن structure/liquidity وناشر worker — ثم بناء الهجرة والمخزن والتوصيل بنفسي (تسريع بعد انقطاعي الوكيلين).
- migrations/versions/0005_orderflow_tables.py: ثلاثة جداول — orderflow_events (§31.3 «امتصاص/إنهاك/دلتا/اختلال» بنفس بنية structure_events: event_id uuid5 حتمي + نوع + أداة + إطار + event_time + payload JSONB + فهارس فريد وزمني) وfootprint_bars (§31.2: المفتاح الطبيعي (أداة، إطار، دلو) هدف upsert — «المتطور يُحدَّث لا يُستنسخ» عقيدة الشموع؛ الأعمدة المسطحة الستة عشر + source_feed وmethodology عمودين إلزاميين §12.7 + payload JSONB) وfootprint_rows (الاحتفاظ المقيد: لا كتابة تلقائية مع كل شريط — «عند الحاجة للبحث أو حدث مكتشف حصرًا»؛ فهرس فريد رباعي؛ التقسيم الفعلي بdate/instrument مؤجل للهدف وموثق).
- services/orderflow/src/orderflow/store.py: FootprintStore — upsert_bar (DO UPDATE على المفتاح الطبيعي) وreplace_rows (حذف-ثم-إدراج داخل معاملة المستدعي — إعادة الإرسال idempotent) وupsert_event (رفض صاخب للأنواع غير التدفقية الثمانية) وread_bars/read_events/read_rows بإعادة بناء النماذج عبر pydantic. flow_event_id محلي بنفس مساحة الاسم (عقود الطبقات تمنع استيراد structure.store — التوثيق في رأس الوحدة).
- worker/analysis_publisher.py: توسعة 4-e — build_envelope ببروتوكول هيكلي EmittedEventLike (خصائص قراءة فقط تغايرية: نوع §20 + وقت التأكيد + حمولة pydantic) فيقبل سجلات البنية (3-b/3-d) والتدفق (4-c/4-d) معًا — الناشر طبقة تركيب محايدة تجاه الكواشف.
- worker/__main__.py: تشغيل تجريبي ثالث (نمط 3-f) يبث ABSORPTION_BUY مثالًا كامل الشروط §12.3 بمرشح غير مؤكد عبر الناشر الموسع على market.event.example.1m.absorption_buy + تبعية engine-orderflow في pyproject (مع تحديث uv.lock).
- الاختبارات التكاملية: test_migrations_0005.py (أعمدة/فهارس الجداول الثلاثة + هبوط إلى 0004 وإعادة صعود — الرأس ديناميكي) وtest_orderflow_store_live.py (upsert شريط مرتين ⇒ صف واحد محدَّث، استبدال صفوف مرتين ⇒ idempotent ومرتبة، حدث مرتين ⇒ صف واحد round-trip بالتطابق، رفض النوع البنيوي، عقد الأنواع الثمانية).
- إصلاحات بوابة أثناء التطوير: أنواع information_schema (character varying لـString)، S603 noqa بنمط 0002، تغاير البروتوكول (خصائص بدل سمات — اتحاد الحمولات يحقق BaseModel)، تعداد الجودة الصريح.
- البوابة: make gate = 1752 passed + 24 integration خضراء (كانت 17) وalembic عند 0005_orderflow_tables (head).

Stage Summary:
- **«الخام خالد في الكائني» يمتد للفوتبرنت**: كل شريط upsert على مفتاحه الطبيعي والصفوف قرار كتابة مقيد بالأحداث المكتشفة (§31.2 حرفيًا) والأحداث التدفقية الثمانية لها موطن orderflow_events بمعرفات uuid5 حتمية (روح D-07).
- **الناشر موحد للتحليل كله**: مسار بث واحد (AnalysisEventPublisher + build_envelope) يخدم البنية والسيولة والتدفق — توسعة بلا كسر (اختبارات 3-f القائمة خضراء كما هي).
- **التالي (4-f)**: بوابة verify_phase4 — المسار الكامل على عينة المرحلة 4 (بناء فوتبرنت من 35,932 صفقة + مطابقة ذهبية دلو-بدلو + كواشف التدفق بالعتبات التطبيعية + الحتمية واللا-نظرة والتحجيج + البث NATS + القاعدة idempotent).

---
Task ID: 4-f
Agent: Main Agent (Z.ai Code — Coordinator)
Task: بوابة خروج المرحلة 4 — verify-phase4 وإغلاق المرحلة (إكمال المنسق: باعث الاستمرار)

Work Log:
- إكمال المنسق للمسار الحدثي للاستمرار: orderflow/continuation.py — ContinuationEmitter ردفف رقيق فوق مصفوفة الجهد/النتيجة (خلية AGREE ⇒ FLOW_CONTINUATION_UP/DOWN بحمولة كاملة القياسات — حدث مباشر عديم الحالة) + 5 اختبارات (الخليتان بالاتجاهين وبقية الخلايا لا تصدر والحتمية وحارس الترتيب).
- scripts/verify_phase4.py + هدف make verify-phase4 — الفحوص التسع على عينة المرحلة 4 الحقيقية (35,932 صفقة): العينة مقابل manifest والمطابقة الإحصائية (buy == takerBuy تمامًا 119/119 + total/sell بتسامح معلن abs=0.5 لدلوي حدود aggTrades + OHLCV في 117 دلو غير متأثر) والمسار الكامل (فوتبرنت + 4 كواشف بالعتبات التطبيعية) والحتمية (هاشان ⇒ 7bba4dce…) واللا-نظرة (بادئة 100 دلو مستقلة) والتحجيج (λ=2 ⇒ نفس توقيع 58 حدثًا) والقانونية (مغلف §32 + مخطط الحمولة لكل حدث) والاكتفاء (توثيق التوزيع: 6 أنواع تطلق و5 مرشحات امتصاص كؤوس confirmed=False) والبث NATS الحي (10 أحداث بتحقق jsonschema) والقاعدة (إرسال مرتين ⇒ idempotent + round-trip بالتطابق).
- قرارات تشغيلية أثناء البوابة: INSTRUMENT يُشتق من الصفقات (هوية موحدة عبر الشموع/الفوتبرنت/الناشر/المخزن)؛ فحص OHLCV يقيد بالدلاء غير المتأثرة بحدود aggTrades (المتأثرة تحكمها تسامحات التدفق)؛ أثر الحدود موثق بالعد فيخرج البوابة.
- ADR-022 في decisions.md: المنهجية الثابتة aggtrade-taker-side-v1 + القاعدة الصفّية المباشرة + المرجع الذهبي والتسامح المعلن + الاحتفاظ الصفّي المقيد.
- progress.md: قسم المرحلة 4 كاملًا (6 صفوف ببواباتها) + سطر جلسة البناء + تحديث المؤشر للمراحل 5-10.
- البوابات النهائية: make gate = 1757 passed + 24 integration + make verify-phase4 خضراء بالكامل.
- وسم phase-4-gate (بروتوكول §F: tag عند كل بوابة خروج) + الرفع إلى GitHub.

Stage Summary:
- **بوابة المرحلة 4 مغلقة رسميًا**: «حسابات التدفق ضمن تسامح معلن مقابل مرجع» محققة حرفيًا (المرجع: البورصة نفسها عبر takerBuyBaseAssetVolume — التسامح: rel=1e-9 للشراء وabs=0.5 معلنًا للإجمالي) و«كل حدث تدفق موسوم بالمصدر والمنهجية» محققة في كل شريط وحدث (§12.7).
- **حصيلة المرحلة**: 8 حمولات أحداث قانونية + بنّاء فوتبرنت حتمي بمنطقة قيمة 70% + 4 كواشف (استمرار/امتصاص/إنهاك/عناقيد) بعتبات تطبيعية + هجرة 0005 بثلاثة جداول + مخزن idempotent + ناشر worker موسع — 1757 اختبارًا كليًا (+346 عن نهاية المرحلة 3) و58 حدثًا حتميًا على عينة حقيقية.
- **التالي بحسب الخطة**: المرحلة 5a — الأنماط (شموع + كلاسيكي) [MVP]: سمات الشموع §13.1 والبُنى الثمانية §13.2 وبوابة الاستئصال (§46-5).

---
Task ID: 5-a
Agent: Main Agent (Z.ai Code — Coordinator)
Task: أسس المرحلة 5a — حمولتا أنماط schemas + سمات الشموع الست في السجل المركزي

Work Log:
- استرداد بيئة R-3 كامل (venv محت بالكامل): uv sync --all-packages → .env من المثال بسر engine-secret → make infra-provision (ثنائيات أُعيد تنزيلها) → إطلاق الأغلفة double-fork (postgres/nats/seaweedfs/migrate/worker كلها ✓ + api healthz 200) → make gate = 1757 خضراء (نقطة البداية). تنظيف 127 تغيير وضع ملفات mode-only أثاثتها عملية الاسترداد السابقة (git restore).
- قراءة §13 كاملاً (شموع 832-884) و§43 (منهج الاستئصال) و§46-5 (بوابة: جهاز الاستئصال قبل التقييم الحي) و§41 (بوابات الترقية) وقاموس §20 (أنواع الأنماط الخمسة وأوزانها).
- schemas/patterns.py: CandlePatternFamily (العائلات الثماني §13.1 حرفياً) + PatternDirection (BULLISH/BEARISH/NEUTRAL) + ClassicalPatternType (10 قيم لثماني عائلات §13.2 — الجهات مفصولة بقرار موثق) + PatternStatus (CANDIDATE/CONFIRMED — «الغامض مرشح يساهم قليلاً أو لا يساهم» §13.2) + CANDLE_FEATURE_KEYS (السمات الست حرفياً) + AnchorPoint (time/price/role بشرط role غير فارغ) + حمولتان: CandlePatternEventPayload (feature_readings بمفاتيح الست حصراً — «الأسماء مستعارات لتركيبات سمات» — strength/bars_in_pattern/direction/family) وClassicalPatternEventPayload (مخرجات §13.2 الثمانية حرفياً: pattern_type/geometry/anchor_points/completion_time/breakout_level/invalidation_level/measured_move/quality + زوج الفشل reclaim_level/failure_speed يحضران معاً أو يغيبان معاً + أنكورات 2..8).
- التسجيل في EVENT_PAYLOAD_MODELS: الأنواع الستة (4 شموعية → CandlePatternEventPayload و2 كلاسيكيان → ClassicalPatternEventPayload) — الخريطة 23→29. الصادرات (__init__ وexport: 32 مخططاً) والتوليد idempotent.
- features/candle_features.py: السمات الست كدوال صرفة عبر quantmath (rolling_percentile/rolling_mean) — body_fraction [0,1] وwick_asymmetry [-1,1] وclose_location [0,1] (فورية بلا دافئ) + range_percentile_100 وgap_relationship_20 وvolume_relationship_20 (نوافذ خلفية شاملة بلا-نظرة). قرارات المدى المنعدم موثقة (0.0/0.0/0.5) وحارس متوسط منعدم ⇒ nan.
- registry.py: فئة CANDLE خامسة + السمات الست مسجلة (الثلاث الفورية بلا معاملات) — الاستئصال 5a.3 سيشغل عبرها.
- الاختبارات: test_schemas_patterns.py (37: round-trip/حدود/جمود/مفاتيح الست/زوج الفشل/أنكورات 2..8/المرشح الغامض/الخريطة 29) وtest_candle_features.py (29: قيم يدوية/دافئ/مدى منعدم/فارغة/حدود خصائص/توصيل السجل A-02 بتطابق بايتي) + تحديث المثبتين: PINNED 17 والفئات 5 وPATTERN_EVENT_TYPES في اختبار البنية (23→29 مفصولة المجموعات).
- إصلاحات بوابة: إعادة توليد المخططات بعد تصحيح العد (docstring التعداد يدخل description المخطط!)، ترتيب RUF022 (__all__)، raw-string لـ2..8، نوع Callable للمعامل factory (mypy strict)، وقيمة متوقعة خاطئة في اختبار volume (النافذة شاملة للقيمة الحالية 140 لا 80).
- البوابة: make gate = 1823 passed (+66) وschemas check = 32 مخططاً idempotent. الالتزام ed35b5b (16 ملفاً، 1501 إدراجاً).

Stage Summary:
- **عقود أسس المرحلة 5a جاهزة للكواشف**: الحمولتان قانونيتان (الشموعية بمفاتيح السمات الست حصراً والكلاسيكية بمخرجات §13.2 الثمانية حرفياً) والسمات الست مسجلة في السجل (فئة CANDLE) — جاهزة للاستئصال 5a.3.
- **عقد الواجهة للوكيلين الموازيين**: 5-b يبني كاشف العائلات الثماني في services/patterns (يستهلك schemas.CandlePatternEventPayload وسمات features) و5-c يبني مكتشف البُنى الثمانية في نفس الحزمة (يستهلك ClassicalPatternEventPayload/AnchorPoint) — كلاهما لا يمس __init__.py للحزمة ولا pyproject.toml (المنسق يدمج الصادرات).
- **قرار معماري حاسم للوكيل 5-c**: عقد استقلال الكواشف يمنع استيراد structure — pivots هندسية محلية داخل patterns (وليست swings البنيوية المؤكدة المتأخرة §11.1 — وظيفياً مختلفة: البُنى الكلاسيكية تحتاج قطوعاً فورية للهندسة).
- **التالي**: 5-b و5-c بالتوازي ثم 5-d (بوابة الاستئصال + verify-phase5) ثم 5-e (إغلاق ووسم ورفع).

---
Task ID: 5-b
Agent: candle-patterns-builder (full-stack-developer) — أُتمم التسليم بيد المنسق بعد انقطاع أمد الوكيل
Task: المهمة 5a.1 (5-b) — العائلات الثماني §13.1 كأسماء مستعارة لتركيبات السمات + كاشف أحداث §20 الثلاثة

Work Log:
- (الوكيل أنجز candle_patterns.py كاملاً (978 سطراً بتوثيق معمق) قبل انقطاع مهلته؛ المنسق راجعه سطراً-بسطر، أصلاح إصلاحين شكليين (ruff format وRUF001 علامة ناقص غامضة)، ثم كتب الاختبارات الناقصة وأتمم الالتزام.)
- البنية: دوال تصنيف صرفة لكل عائلة (classify_engulfing/rejection/hammer_shooting_star/inside_bar/inside_bar_break/doji/morning_evening_star/strong_closing/expansion + classify_last_candle بالترتيب الحتمي لـ§13.1) + CandlePatternConfig بعتبات نسبية موثقة كلها + بوابة دافئ موحدة (السمات الست محدودة كلها عند شمعة القرار وإلا لا تصنيف — عقد التركيبة المستعارة كاملة الظهور) + CandlePatternDetector (آلة تتابعية بنمط imbalance: شموع مغلقة، هوية واحدة، ترتيب صارم، بث الأنواع الثلاثة ذات الأحداث في §20 حصراً بترتيب عائلات §13.1، العائلات الخمس الباقية تصنيف سياقي غير مبثوث).
- قياسات §20 العمودية موثقة: Body ratio للابتلاع (جسم المبتلعة/الجسمين — الصورة المستقرة r/(r+1)) وWick ratio للرفض وتباين الانضغاط-فالتوسع لكسر الداخلية ((مئيني الكاسر − مئيني الأم + 1)/2).
- قرارات موثقة أبرزها: الألوان المتعاكسة شرط الابتلاع الكلاسيكي (منع عد الاستمرار ابتلاعاً)؛ الاحتواء غير الصارم؛ كسر الداخلية بالإغلاق حصراً (مسبار الذيل ليس كسراً)؛ النجمة بلا شرط فجوة (أسواق 24/7 المتصلة — gap_relationship تبقى في القراءات)؛ INSIDE_BAR direction=NEUTRAL قبل الكسر بعقد PatternDirection.
- الاختبارات (56): قيم يدوية محسوبة لكل عائلة + نقيض مانع مستقل لكل عائلة + الأحداث الثلاثة بحمولات دقيقة + الحتمية + اللا-نظرة (بادئة ⊆ كامل) + لا-إعادة-بث + الدفعة==شمعة-بشمعة + الحرس الأربعة + الهوية (التقاط/ناقصة ترفض).
- إصلاحات منسق أثناء الدمج: فهارس زمنية متسلسلة (الهندسات الملحقة بالدافئ كانت تعيد الفهارس للخلف — رفض عقد الاتساق)، قيم محسوبة (نافذة الحجم الشاملة للقيمة الحالية 140 لا 80، جسم الإغلاق القوي 9 لا 8، جسم النجمة 0.2 بمدى 2)، تضييق mypy في اختبار الهوية، RUF005 تفكيك آلي.
- البوابة بعد الدمج: make gate = 1879 passed. الالتزام 2e6095a (سلفاً) + إصلاح 6209e8a.

Stage Summary:
- **بوابة 5a.1 نصاً**: fixtures لكل عائلة من الثماني (موجبة بقياس قوة يدوي + نقيض مانع مستقل) ✓ — والأحداث القابلة للبث الثلاثة قانونية بحمولة 5-a (feature_readings بمفاتيح الست حصراً).
- **عقد الواجهة**: التصنيف الصرف (classify_last_candle) للاستئصال والسمات، والكاشف للبث — الدمج (fusion §19) يقرأ أحداثه لاحقاً.

---
Task ID: 5-c
Agent: classical-patterns-builder (full-stack-developer — منفذ فعلياً: المنسق بعد انقطاع الوكيل قبل أي كود)
Task: المهمة 5a.2 (5-c) — البُنى الكلاسيكية الثماني §13.2 بمخرجاتها الثمانية + هندسات مثالية وغامضة

Work Log:
- الوكيل انقطع قبل إنتاج أي كود — المنسق نفذ المهمة كاملة مباشرة: classical.py (840 سطراً) + test_classical.py (38 اختباراً).
- find_pivots: قطوع هندسية محلية fractal بقوة خلفية k (تعاقب صارم — متتاليان بنفس النوع يبقى أقصاهما) — القرار المعماري الملزم منفذ: لا استيراد structure إطلاقاً (عقد استقلال الكواشف) — وثق الفرق عن swings §11.1 في رأس الملف.
- بناة المرشحات بترتيب أولوية موثق: _try_hs (خمس قطوع: بروز رأس + تقارب كتفين + رقبة متحفظة min) ثم _try_double (ثلاث: تطابق طرفين + عمق رقبة) ثم _try_lines (أربع: تصنيف بالميلين — إشارتان مختلفتان مثلث/بنفس الإشارة متقارب إسفين أو متوازٍ قناة/شبه أفقيين نطاق — باستقراء خطي للكسر الجهوي) ثم _try_flag (عمود قوي فتجميع ضيق — العمود آخر pole_min_bars شموع حصراً: قرار موثق بعد اكتشاف خلل قياسه من قاع النافذة كلها).
- الكاشف ClassicalPatternDetector: مرشح نشط واحد (بصمتا بناء ضد الرفرفة §27: بصمة القطوع تمنع إعادة بناء نمط مكسور بقطوعه، وبصمة العلم تمنع تكرار تجميعه) + دورة حياة (بناء ← كسر بهامش معلن ← فتح نافذة فشل ← إبطال صامت بلا بث عند تجاوز حد البطلان — لا نوع للإبطال في §20) + CLASSICAL_FAILED_BREAKOUT بزوجه (reclaim_level + failure_speed بعدّاد أشرطة لا فهارس مطلقة — قرار بعد اكتشاف كسر الفهارس بقص النافذة).
- أربع علل منطقية اكتشفها المنسق بالتشخيص التدريجي وأصلحها: (1) شرطا أنواع معكوسان في _try_hs و_try_lines يرفضان كل هندسة صحيحة (التعاقب المتناوب يجعل الكتفين والرأس بنفس النوع بالضرورة)؛ (2) موت المرشح لا يستأنف البناء بنفس الشمعة (تدفق on_candle)؛ (3) عدّاد الفشل يزاد بعد الفحص (سرعة خاطئة)؛ (4) هدف العلم المقاس كان عرض التجميع (الصحيح: ارتفاع العمود §13.2).
- الاختبارات (38): zigzag builder (ذيل أعرض 1.5× عند الانعطاف يضمن القطع) بأسعار قطوع فعلية محسوبة يدوياً — لكل بنية من الثماني هندسة مثالية بمعادلات §13.2 الحرفية + مرايا (قاع مزدوج/معكوس الرأس والكتفين) + الغامض CANDIDATED (q=0.3 لتفاوت 9%) يبث إن انكسر + كسر فاشل بزوجه + نافذة تنقضي + غير مكسور لا يبث + الحتمية + اللا-نظرة (بادئة بحدث كسر ⊆ كامل) + الدفعة==شمعة-بشمعة + مخرجات الثمانية حاضرة + geometry رقمية حصراً + الحرس الستة.
- البوابة: make gate = 1919 passed (ruff + mypy strict 150 ملفاً + import-linter 6 عقود + pytest) وlint-imports خضراء.

Stage Summary:
- **بوابة 5a.2 نصاً**: «هندسات مثالية + غامضة تبقى مرشحة ضعيفة» ✓ بثمانية أنماط مبثوثة عبر حدثي §20 (الكسر والكسر الفاشل) بمخرجات §13.2 الثمانية حرفياً بالأسماء.
- **قرارات معمارية للاستزادة**: pivots هندسية فورية مستقلة عن البنية؛ المرشح الواحد بترتيب أولوية (رأس وكتفان ← مزدوج ← خطوط ← علم) — النطاق متطابق الحواف يُلتقط غالباً مزدوجاً (وصف أدق محلياً، موثق في الاختبار)؛ الإبطال صامت بلا بث.
- **التالي (5-d)**: بوابة الاستئصال — مقيم حقيقي قابل للحقن (طاقة تنبؤية OOS بتقسيم زمني) + سجل promotion-like بحقول §41 المتاحة + verify_phase5 (أنماط + استئصال + بث + قاعدة pattern_events).

---
Task ID: 5-d
Agent: Main Agent (Z.ai Code — Coordinator)
Task: بوابة خروج المرحلة 5a — المقيّم الحقيقي + سجل الترقية + verify-phase5 (§46-5)

Work Log:
- توسعة store.py: أنواع المرحلة 5a الستة انضمت لـPATTERN_EVENT_TYPES (توسعة مشروعة بنمط 3-f) — مخزن AnalysisEventStore جاهز لاستقبال أحداث الأنماط بلا مساس.
- engine_replay/ablation_evaluator.py (المقيّم الحقيقي — الوفاء بالوعد المؤجل في 2-e): AblationEvaluatorConfig (horizon=5, train_ratio=0.70, signal_quantile=0.90) + خريطة FEATURE_POLARITY المعلنة (close_location موجبة وwick_asymmetry معكوسة وgap_relationship موجبة؛ الثلاث غير الموجهة مطلقة الاستجابة حصراً) + evaluate_directional الصرفة: عتبات كوانتيلية من التدريب حصراً (لا تسرب معلومي)، القياس في OOS، مقاييس المجموعة oos_signal_count/oos_absolute_response_median/oos_directional_hit_rate_median مع حذف المفاتيح عند غياب القياس (القاعدة الفارغة تعيد خريطة فارغة) + DirectionalEvaluator القابل للحقن في MetricEvaluator (يحسب عبر compute_feature — المسار الوحيد A-02).
- scripts/verify_phase5.py + هدف make verify-phase5 — الفحوص العشرة: العينة الثلاثية الأطر (عد + شاوم) والمسارات (شموعي 454 حدثاً على 1m بتوزيع معلن، كلاسيكي 112 عبر الأطر: 1m=106 و15m=1 و1h=5 كلها قانونية) والحتمية (مساران لكل كاشف بهاشات 8f3d5e36…/6c2e9eb9…/958c61e9…/6fdb0939…) واللا-نظرة (بادئة 200) والتحجيم λ=2 (نفس الأحداث — عتبات §13 نسب) والقانونية §32 (تسلسل JSON كامل — درس بوابة 3) ومخرجات §13.2 الثمانية مستعلة من الحمولات وبوابة الاستئصال (الجدول base+6 كاملاً و6/6 قاست إشارات فعلية في OOS والتقرير حتمي بايت-بايت بساعة محقونة) وسجل الترقية (docs/ablation/phase5a/: promotion_record.json بحقول §41 المتاحة + ablation_report.json) والبث NATS (9 أحداث عبر 5 أنواع بتحقق jsonschema) والقاعدة (pattern_events ×2 idempotent + round-trip عبر النماذج).
- سجل الترقية promotion-like بحقول §41: code_commit (git rev-parse عند الأرشفة) وfeature_schema (الست) وparameter_set وtraining_window/oos_window (فترات فعلية من التقسيم) وdata_source_versions (من العينة) وmodel_artifact_hash (sha256 التقرير) وapproval_timestamp — وcost_model/calibration_artifact مؤجلان صراحة بأسبابهما (مرحلتا 7/9 — «لا اختلاق»).
- خمس علل شُخّصت وأصلحت أثناء تشغيلات البوابة: (1) حمولة فشل الكسر كانت تنسخ قيم مرشح خطي غير محسومة (0.0 يرفضه Price) — خزنت قيم الحدث الفعلية في _BreakState؛ (2) فحص القانونية بـmodel_dump يترك datetime كائنات — تسلسل JSON كامل؛ (3) مواضيع الاشتراك بُنيت يدوياً وخالفت بناء الناشر من instrument الحمولة — subject_for الرسمية؛ (4) اشتراكات مكررة ضاعفت الاستقبال — مواضيع فريدة؛ (5) round-trip: JSONB لا يحفظ ترتيب مفاتيح الـdict — إعادة البناء عبر النماذج ثم sort_keys (والقراءة بالمعرف المشتق من هوية الحمولة نفسها).
- البوابات: make gate = 1919 passed وintegration 23+1 skipped وmypy strict على 151 ملفاً وmake verify-phase5 خضراء كاملة.

Stage Summary:
- **بوابة المرحلة 5a مغلقة**: «جهاز الاستئصال موجود قبل السماح لهذه السمات بالتقييم الحي» (§46-5) محققة حرفياً بالمقيّم الحقيقي والسجل المؤرشف — والمرحلة 6 (دمج الدليل §19) تستطيع استهلاك أحداث الأنماط بثقة أن قيمتها التنبؤية مقيسة OOS.
- **حصيلة المرحلة**: 1919 اختباراً (+162 عن نهاية المرحلة 4) و566 حدثاً حتمياً (454 شموعياً + 112 كلاسيكياً) على بيانات حقيقية عبر ثلاثة أطر، وسمات الشموع الست مسجلة قابلة للاستئصال، وسجل ترقية قابل للتراكم عبر المراحل.
- **التالي بحسب الخطة**: المرحلة 6 — دمج الدليل (سجل §19.1 + الحساب بمعادلة c_i ورياضيات D-03 + مجموعات الارتباط + التناقض + التفسير §2.8).

---
Task ID: R-4
Agent: Main Agent (Z.ai Code — Coordinator)
Task: التحقق من التقدم بحسب الخطة + استرداد البيئة بعد محو المنصة (R-4) + إعادة إثبات بوابات 5a

Work Log:
- طلب المستخدم: التحقق من التقدم بحسب الخطة وتحديد المرحلة التالية — البعيد مصدر الحقيقة.
- git fetch: البعيد عند c03f04b (بوابة 5a + إصلاحا القيم الفعلية للكسر الفاشل وهدف verify-phase5 في Makefile) والمحلي كان متقدماً بالتزام ضجيج UUID واحد (e102a08 يحتوي .zscripts/dev.pid حصراً) + تغييرات صلاحيات mode-only + ملفا ضجيج — تحقق المحتوى ثم reset --hard origin/main (لا فاقد).
- محو المنصة للبيئة مجدداً (R-4): venv فارغ تماماً و.env مفقود وdata/ كلها ضائعة (ثنائيات + بيانات postgres + سجلات) — نفس نمط R-1/R-3.
- استرداد كامل بالبروتوكول المعتمد: uv sync --all-packages ✓ → .env من المثال بسر engine-secret ✓ → make infra-provision (nats + postgres Zonky + seaweedfs) ✓ → إطلاق الغلافين double-fork (engine-infra + engine-api) ✓.
- الصحة: postgres ✓ nats ✓ seaweedfs ✓ migrate EXITED_OK (الرأس 0005_orderflow_tables) ✓ worker HEALTHY ✓ — وAPI healthz 200.
- إعادة إثبات البوابات على البيئة المستردة: make gate = 1919 passed + integration 24 passed + make verify-phase5 خضراء كاملة (566 حدثاً حتمياً والاستئصال 6/6 OOS وسجل الترقية والبث والقاعدة idempotent).
- إعادة تشغيل verify-phase5 جدّدت promotion_record.json بطابع زمني جديد — استعيد السجل المؤرشف الرسمي (git checkout) لأنه وثيقة إغلاق البوابة لا ناتج كل تشغيل.
- تنظيف نهائي: working tree نظيف (0 تغييرات) والمحلي == origin/main (c03f04b) والوسمان phase-4-gate وphase-5a-gate موجودان.

Stage Summary:
- **الحالة المكتملة**: المراحل 0 و1 و2 و3 و4 و5a كلها مغلقة البوابات ومرفوعة إلى GitHub (آخر التزام c03f04b) — 1919 اختباراً و32 مخططاً و21+ADR (آخرها ADR-023).
- **المرحلة التالية بحسب الخطة**: المرحلة 6 — دمج الدليل (§19): سجل الدليل 6.1 + حساب c_i برياضيات D-03 (6.2) + مجموعات الارتباط وخصم الاستقلالية (6.3) + التناقض (6.4) + التفسير §2.8 (6.5) — بوابة الخروج: كل سيناريو يعرض سلسلة دليله كاملة باستعلام واحد.
- **5b الهارمونيك مؤجل صراحة** بحسب الخطة (خارطة بعد MVP بنفس أسلوب §14).
- البيئة حية ومثبتة والخادم الأمامي على 3000 يستجيب 200 — بانتظار إشارة المالك لبدء المرحلة 6.

---
Task ID: 6-0
Agent: Main Agent (Z.ai Code — Coordinator)
Task: قراءة مواصفات المرحلة 6 (§19 + §2.8 + D-03 + §20 + §31.3) وتصميم معمارية محرك الدمج

Work Log:
- قراءة §19 كاملاً (سجل الدليل 19.1 بالمساهمة c_i 19.2، المجموعات الست وحصصها 19.3، التحكم بالارتباط 19.4، نموذج التناقض 19.5، الاحتمال المعاير 19.6) و§2.8 (كائن التفسير بعشرة حقول) وجدول §20 كاملاً (45 نوعاً بأوزانها) وقرار D-03 (سقف tanh لكل مجموعة + إعادة توزيع حتمية عند الخلو + التناقض دليل معاكس صريح + veto خارج الحساب كلياً + كلها في parameter_sets مُصدَّرة) و§31.3 (جدولا evidence_items والسيناريوهات).
- جرد الأصول القائمة: EvidenceRecord وEvidenceGroup وDEFAULT_GROUP_SHARES (§19.3 حرفياً) وEventType (45) وDEFAULT_EVENT_WEIGHTS (§20 حرفياً) وScenario (§18.1 بسلسلة الدليل) كلها من المرحلة 0 — خدمات fusion/scenarios هياكل فارغة — طبقة fusion في عقد import-linter جاهزة («الدمج مسؤولية fusion وحدها»).
- فحص الحمولات الـ29 الموثقة (بنية/سيولة/تدفق/أنماط) واستخلاص جدول قطبية/قوة لكل نوع من حقول الحمولة نفسها (لا اختراع): كسور البنية من break_direction وbreach_distance_atr، الاجتياح BUY_SIDE مرفوضاً = قطبية هابطة (تأكيد من كود الكاشف: الاسترجاع إغلاق دون الحافة)، الامتصاص من absorbed_pressure (SELL→صاعد)، الإنهاك ضد اتجاه الجهد المنهك، الموقع premium=−1/discount=+1، الكلاسيكي الفاشل ضد اتجاه الكسر...
- القرارات المعمارية (توثق في ADR-024 عند الإغلاق): (1) direction_score نسبي للسيناريو ±1 فيسري التناقض بإشارة c_i نفسها (§19.5 بالحرفية)، (2) HTF bias دليل مشتق من الحالة (المصدر market_state.htf_bias — §9.2 يسميه «contextual evidence» حرفياً)، (3) مجموعة الارتباط = نفس (أداة، إطار، شريطة التأكيد) والخصم الهندسي γ^(k−1) بترتيب |c_i|، (4) الإتاحة = وجود عضو مؤهل |c_i|>0 (D-03-أ «الأعضاء المؤهلين»)، (5) freshness تضمحل خطياً على ttl = عدد أشرطة × مدة الإطار، (6) quality=1.0 موثقة (بوابات التنقيح أعلى المجرى تمنع الشموع الرديئة من الوصول للكواشف)، (7) saturate(x)=x/(1+x) للقياسات غير المحدودة، (8) جدول fusion_snapshots امتداد موثق ل§31.3 (لوحة §35.3 تحتاج أثر الاستدلال مؤرشفاً)، (9) evidence_id حتمي uuid5(scnario|event) وevent_id يقبل NULL للدليل المشتق من الحالة.

Stage Summary:
- التصميم جاهز بالكامل: fusion = مكتبة نقية (mapping/ledger/compute/explain/store + parameter_sets) فوق schemas/common فقط — لا NATS حي في هذه المرحلة (الدمج مستهلك لا منتج أحداث؛ التوصيل الحي مع مقترحات المرحلة 7) — والبوابة «سلسلة الدليل باستعلام واحد» عبر JOIN واحد على evidence_items⟕fusion_snapshots.
- الأحداث الـ29 الموثقة الحمولات هي الوقود الفعلي؛ الـ16 الباقية (HTF كحدث، POC/VA، الهارمونيك، الجلسات كأحداث، الحجب الصلب) موطنة في الخريطة بلا حمولات — غياب الحمولة إعلان صريح لا صمت موافقة.
- التالي: 6.1 (schemas + mapping) ← 6.2 (parameter_sets + compute) ← 6.3 (ledger) ← 6.4+6.5 (explain) ← هجرة 0006 + مخزن ← verify-phase6 ← إغلاق.

---
Task ID: 6-e و6-f
Agent: Main Agent (Z.ai Code — Coordinator)
Task: هجرة 0006 والمخزن والسلسلة باستعلام واحد (6-e) + بوابة الخروج verify-phase6 والإغلاق (6-f)

Work Log:
- migrations/0006_fusion_tables.py: evidence_items (§31.3 «Every evidence input to fusion» — 18 عموداً مسطحاً منها contribution المسهولة + payload JSONB + event_id يقبل NULL لدليل الحالة) وfusion_snapshots (امتداد ADR-024: أثر الاستدلال §35.3) بفهرس السلسلة (scenario_id, event_time) والفريد (scenario_id, fusion_time).
- fusion/store.py: FusionStore — upsert_evidence/upsert_snapshot idempotent (المساهمة يحسبها المخزن بالمعادلة الرسمية) وread_chain جولة SQL واحدة (json_agg للأدلة بترتيب حتمي + أحدث لقطة) وread_snapshots للتاريخ — 9 اختبارات تكاملية بينها قياس الجولة الواحدة بعدّاد فعلي.
- EvidenceRecord توسع بامتدادين موثقين (نمط correlation_group_id): event_time وevent_id — والباني يملؤهما والاشتقاق محلي بنفس مساحة أسماء structure/orderflow.
- scripts/verify_phase6.py (20 فحصاً): العينتان + الأحداث عبر العائلات الأربع على بيانات حقيقية (1696 حدثاً بـ27 نوعاً) + c_i بإعادة حساب مستقلة + السقوف على لحظتي قرار + حقنة الدفعة الواحدة حرفية البوابة + 387 دفعة حقيقية مخصومة + إعادة التوزيع باتجاهيها (A-01 حي) + التناقض يخفض ولا يلغي + veto بلا مساس رقمي + الحتمية بايت-بايت + لا-نظرة (بادئة مستقرة) + λ=2 بمقارنة دلالية (القيم وأعضاء الدفعات وتوزيع الخصومات منفصلين عن الهويات) + القانونية (jsonschema) + المعايرة المؤجلة موثقة + التفسير §2.8 بالفحص الآلي + السلسلة الحية باستعلام واحد (1696 سجلولاً ولقطة بجولة واحدة).
- **خللان جوهريان اكتشفتهما البوابة وأصلحهما**: (1) معرفات الأحداث الحتمية كانت تتصادم للأحداث متعددة المناطق عند الشمعة نفسها (47 زوجاً في العينة — تصادم كتابة صامتة في مخازن 3-5 منذ المرحلة 3): المعرف توسع ببصمة الحمولة payload_digest في schemas.envelope وعبر structure/orderflow stores والناشر وباني السجل، والبوابات 3/4/5 أعيد إثباتها خضراء بعده. (2) مسار التدفق في البوابة كان صامت الإفراغ (صفقات phase4 لا تتقاطع زمنياً بشموع phase2): لحظتا قرار A/B منفصلتان بمسارهما الصحيح.
- Makefile: هدف verify-phase6 (وأصلح استبدال عرض أفسد tabs الوصفات).
- الإغلاق: ADR-024 (خمسة قرارات: السقف الفعال + لحظتا القرار + مقارنة λ الدلالية + بصمة الحمولة + جدول اللقطات) وقسم المرحلة 6 في progress.md وسطر الجلسة ومزامنة engine/docs.

Stage Summary:
- **بوابة المرحلة 6 مغلقة رسمياً**: make gate = 2070 اختباراً (منها 151 اختبار دمج) + integration 33 + verify-phase6 بعشرين فحصاً أخضر على بيانات حقيقية — «كل سيناريو يعرض سلسلة دليله كاملة (استعلام واحد)» محققة حرفياً بقياس فعلي.
- **حصيلة المرحلة**: 6 وحدات fusion (mapping/ledger/compute/explain/store/parameter_sets) + 5 عقود مخططات جديدة (37 إجمالاً) + هجرة 0006 بجدولين + إصلاح جوهري لهوية الأحداث عبر المستودع كله (ADR-024) — والدرجة الخام للعينة B: LONG ‑0.6065 / SHORT +0.6065 (ليست احتمالاً).
- **التالي بحسب الخطة**: المرحلة 7 — محرك السيناريوهات (D-04: المُقترِحات عند مواقع + أحداث مؤكدة ودورة الحياة §18.2 والمشغل والإبطال والتنافس) — fusion جاهزة لاستهلاكها بالمقترحات.

---
Task ID: 7-0
Agent: Main Agent (Z.ai Code — Coordinator)
Task: قراءة مواصفات المرحلة 7 (D-04 + §18 + §21.2 + §38.2 + §31.3) وتصميم معمارية محرك السيناريوهات + استرداد البيئة R-5

Work Log:
- تحقق الحالة: البعيد عند 0bb415a (بوابة 6 مغلقة ومرفوعة) والمحلي مطابق — 161 تغييراً معلقاً كلها ضجيج (160 mode-only + سطر arrival-log) فنُظف reset --hard.
- محو المنصة مجدداً (R-5 — النمط الرابع): venv و.env والثنائيات ضائعة — استرداد بالبروتوكول: uv sync --all-packages + .env + make infra-provision + إطلاق الغلافين double-fork — كل الخدمات HEALTHY والرأس 0006_fusion_tables.
- إعادة إثبات البوابات على البيئة المستردة: make gate = 2070 passed + make verify-phase6 = 20 فحصاً أخضر.
- قراءة المواصفات كاملة: §18.1-18.5 (كائن السيناريو ودورة حياته الاثنتي عشرة حالة وبناءه التسعي العناصر وترقيته وإبطاله) + §21.1/21.2 (السلاسل السببية والقوالب الثلاثة) + D-04 (مقترحات حتمية معددة من حدث مؤكد عند موقع مرسوم) + §38.2 (خصائص دورة الحياة) + §31.3 (جدولا scenarios وscenario_transitions) + §10.5 (خريطة الأهداف) + §33.4 (الدليل ← السيناريو).
- جرد الأصول: Scenario/ScenarioState(12)/TriggerDefinition/InvalidationRule/TargetZone/PriceZone كلها من المرحلة 0 — حزمة scenarios هيكل فارغ — عقد import-linter يضع scenarios في طبقة القرار فوق fusion والكواشف.
- القرارات المعمارية (توثق في ADR-025 عند الإغلاق):
  (1) القوالب الثلاثة تُستنسخ من حدثين سيوليين موقعيين حصراً (اجتياح مؤكد أو كسر-قبول — كلاهما يحمل zone_id): REVERSAL ضد جهة الاجتياح بمشغل إزاحة LTF، وBREAKOUT باتجاه الاختراق (من الاجتياح: قبول خلف القاع الحتمي؛ من الكسر-القبول: صمود إعادة الاختبار)، وCONTINUATION باتجاه انحياز HTF المؤكد فقط (غياب الانحياز المؤكد = غياب موثق لا صمت).
  (2) إعادة اشتقاق قاع الاجتياح الحتمي من الحمولة: الحافة البعيدة ± excursion_atr×ATR لحظة الحدث (المقاسة خلف البعيدة حرفياً في الكاشف) — الأساس البنيوي لإبطال REVERSAL وحد ACCEPTANCE_BEYOND.
  (3) تفعيل DRAFT→ACTIVE: مجموعتان دالتان (score>0) على الأقل من snapshot.group_scores + لا veto (§18.4 حرفياً) — العدد 2 ثابت مواصفة لا معامل إعدادي.
  (4) حارس الانجراف §18.4 (تحرك بعيداً عن الدخول): مشغل يُرصد مع انجراف > max_entry_drift_atr ⇒ INVALIDATED بالشرط 6 من §18.5 (ظروف تنفيذ مختلفة بنيوياً) — الجزء «المكلف» يُستكمل بالمرحلة 8 موثقاً.
  (5) التنافس: سيناريوهات TRIGGERED متضادة الاتجاه لأداة واحدة تُحسم بالأسبقية الحتمية (مجموعات داعمة تنازلياً ثم الدرجة ثم scenario_id) — الخاسر SUPPRESSED بسبب صريح يسمي الفائز (لا إلغاء صامت).
  (6) ترتيب التقييم داخل الشريط (حتمي موثق): جودة البيانات ← انقضاء ← إبطال ← ترقية ← مشغل ← تنافس.
  (7) scenario_score = (raw_evidence_score + 1)/2 إعادة إسقاط حتمية موثقة ([0,1] حقل المرحلة 0) — ليست احتمالاً (§2.6).
  (8) امتداد Scenario بنمط EvidenceRecord الموثق: template + proposed_from_event_id (هوية D-04) — والمعرف uuid5(القالب|الحدث|المنطقة|الاتجاه).
  (9) خمسة أنواع مشغلات قابلة للرصد: DISPLACEMENT_CONFIRM وINTERNAL_BOS (من أحداث البنية) وACCEPTANCE_BEYOND وRETEST_HOLD وZONE_RECLAIM (آلات حالة شريطية على شموع إطار التنفيذ).
  (10) غياب هدف §10.5 في جهة السيناريو = لا استنساخ للقالب (§18.3 إلزامي — إعلان صريح).

Stage Summary:
- التصميم جاهز: scenarios = parameter_sets + templates + proposer + lifecycle + triggers + invalidation + competition + engine + store فوق schemas/fusion/liquidity (العقد يسمح) — هجرة 0007 بجدولي §31.3 — verify-phase7 بنمط verify_phase6.
- البيئة حية والبوابات خضراء — التنفيذ يبدأ بـ schemas (TemplateKind + ScenarioTransition + الامتدادان) ثم الحزمة كاملة.

---
Task ID: 7-كلها (7.1 حتى الإغلاق)
Agent: Main Agent (Z.ai Code — Coordinator)
Task: تنفيذ المرحلة 7 كاملة — محرك السيناريوهات (D-04 + §18) وإغلاق بوابة الخروج 7

Work Log:
- schemas: ScenarioTemplate (§21.2) وScenarioTransition (§31.3 بمدقق سبب جوهري) وامتداد Scenario بنمط ADR-024 الموثق (template + proposed_from_event_id) — 38 مخططاً مصدرة.
- parameter_sets: ScenarioConfig (الزعنفة لكل قالب بأشرطة إطار التنفيذ وعازلة الإبطال وسقف الانجراف ونافذة القبول ونطاق إعادة الاختبار) ببصمة sha256.
- templates: السلاسل السببية §21.2 الحرفية واشتقاق الاتجاهات من الحمولات (دوال صرفة) وأحداث المراسِم الأربعة الموقعية.
- proposer: استنساخ D-04 — REVERSAL/CONTINUATION/BREAKOUT من الاجتياح والكسر-قبول بالهندسة الكاملة (القاع الحتمي المعاد اشتقاقه من الحافة البعيدة ± excursion×ATR) وأهداف §10.5 كحواف الدخول القريبة ودليل الولادة من سجل الدمج وغيوب موثقة (انحياز/هدف).
- lifecycle: الخريطة القانونية للـ12 حالة (الدرب السبعي + النهايات الست بلا صادرة أبدًا) وapply_transition نسخ مجمّدة + سجل ملحق-فقط.
- triggers: خمس آلات حالة شريطية قابلة للرصد (إزاحة/BOS داخلي من أحداث البنية وقبول خلف مستوى/صمود إعادة اختبار/استرجاع منطقة من الإغلاقات).
- invalidation: الحارس الخمسي §18.5 بحكم منظّم يميز نهايات §18.2 (EXPIRED/CANCELLED/INVALIDATED) والحدث المعاكس مشروط بأطروحات الرفض حصرًا وحارس انجراف §18.4.
- competition: مفتاح أسبقية كلي حتمي وSUPPRESSED بسبب يسمي فائزه (قرار أزواج موضوعي).
- engine: القيادة الشريطية بترتيب حتمي موثق (جودة ← إبطال ← ترقية §18.4 ← مشغل ← تنافس) وتغذية أحداث idempotent وحرس جودة عند المرسِم (كلاهما خللان اكتشفتهما البوابة وأُصلحا).
- store + هجرة 0007: جدولا scenarios وscenario_transitions (§31.3) وScenarioStore idempotent وread_lifecycle جولة SQL واحدة وaudit_licensing_readiness (بوابة الخروج نصًا).
- اختبارات: 105 اختبارات وحدة وخصائص جديدة (proposer 23 + lifecycle 23+خصائص FSM + triggers 20 + invalidation/competition 20 + engine 14) + 5 تكاملية + تحديث اختبارات schemas الحدية.
- verify_phase7 (18 فحصاً) + هدف Makefile: على 1440 شمعة حقيقية — 285 مرسِماً و559 مقترحًا و214 ترقية و105 اشتعالات و877 انتقالًا قانونية + الحتمية واللا-نظرة وλ=2 والقانونية وحقن الجودة والقاعدة الحية والبث NATS والتفسير §2.8 بحقول المرحلة 7.
- البوابات: make gate = 2175 passed (+105) وintegration 38 (+5) وmypy strict 182 ملفاً وimport-linter 6 عقود وschemas check 38 مخططاً وverify-phase7 = 18 فحصاً أخضر.
- الإغلاق: ADR-025 (تسعة قرارات) وقسم المرحلة 7 في progress.md وسطر الجلسة ومزامنة engine/docs.

Stage Summary:
- **بوابة المرحلة 7 مغلقة رسمياً**: «لا سيناريو يُرخّص صفقة بلا مشغل وإبطال معرّفين» محققة بالفحص الآلي على القاعدة الحية (صفر مخالفين) — والمحرك يثبت نفسه على بيانات حقيقية بكل مساره (توليد ← ترقية ← اشتعال ← تنافس ← نهايات موثقة).
- **حصيلة المرحلة**: حزمة scenarios كاملة (9 وحدات) + هجرة 0007 + 38 مخططاً + امتداد Scenario الموثق + 105 اشتعالات حقيقية على العينة.
- **التالي بحسب الخطة**: المرحلة 8 — لا-تداول + مخاطرة (الحجب الصلب الخمسة عشر §22.1 والكتم اللين §22.2 ووحدة R والتحجيم §23 والإبطال البنيوي والتكاليف الصافية §25.2 ودفتر التجارب §29.1) — TRIGGERED الجاهزون بصورتهم النهائية موثقة هم مدخله.

---
Task ID: R-6 (جولة تحقق + استرداد)
Agent: Main Agent (Z.ai Code — Coordinator)
Task: التحقق من التقدم بحسب الخطة والحالة الحالية وتحديد المرحلة التالية (طلب المستخدم) — تضمن استرداد البيئة المحية

Work Log:
- تحقق Git: المحلي = البعيد عند 14c15ad (0/0) — الوسوم phase-4/5a/6/7-gate كلها موجودة — 181 تغييراً معلقاً كلها ضجيج (160 mode-only + arrival-log + tool-results) نُظفت بـ reset --hard — شجرة نظيفة.
- الحسم التاريخي: المرحلتان 6 (0bb415a) و7 (14c15ad) مغلقتان رسمياً ومرفوعتان وموثقتان في progress.md — الالتزام 63e5abd رسالة UUID داخل الشجرة (إدخال سجل عمل قديم) لا يمس الكود.
- محو المنصة مجدداً (R-6 — النمط السادس): venv و.env والثنائيات ضائعة والخدمات كلها متوقفة — الاسترداد: uv sync --all-packages ثم .env من المثال ثم make infra-provision ثم إطلاق الغلافين double-fork.
- الصحة بعد الاسترداد: supervisor health سليم (postgres ✓ nats ✓ seaweedfs ✓ migrate EXITED_OK worker HEALTHY) + engine-api healthz 200 + alembic عند 0007_scenario_tables (الرأس).
- إعادة إثبات البوابات على البيئة المستردة: make gate = 2175 passed + make verify-phase7 = 18 فحصاً أخضر + integration = 38 بنداً (37 passed + 1 skipped) — كلها مطابقة لأرقام إغلاق المرحلة 7 حرفياً.
- قراءة قسم D من build_plan.md: المرحلة التالية هي 8 — لا-تداول + مخاطرة (§22.1 الحجب الصلب الخمسة عشر، §22.2-22.3 الكتم اللين والتفسير، §23.1-2 وحدة R والتحجيم، §23.4 الإبطال البنيوي، §25.2 التكاليف الصافية، §29.1 دفتر التجارب كتابةً) وبوابة خروجها: اختبار حقن شامل 15/15.

Stage Summary:
- الحالة مؤكدة بالكامل: المراحل 0-7 مغلقة (7 بوابات موسومة) والبيئة حية مستردة والبوابات مثبتة خضراء — لا انحراف بين المحلي والبعيد والوثائق.
- المرحلة التالية بحسب الخطة: المرحلة 8 (لا-تداول + مخاطرة) — مدخلاتها TRIGGERED الجاهزون من المرحلة 7 بصورتهم النهائية الموثقة.
- لم تُكتب أي شيفرة جديدة في هذه الجولة (طلب تحقق) — لا التزام جديد مطلوب (الشجرة نظيفة عند رأس البعيد).

---
Task ID: 8-0
Agent: Main Agent (Z.ai Code — Coordinator)
Task: قراءة مواصفات المرحلة 8 كاملة (لا-تداول + مخاطرة) وتصميم معمارية المخاطرة ودفتر التجارب

Work Log:
- قراءة §22 كاملاً (الحجب الصلب الخمسة عشر حرفياً + الكتم اللين العشرة + كائن تفسير الرفض سداسي الحقول) + §23 كاملاً (وحدة R + التحجيم بستة معدلات + القيود العشرة + الإبطال البنيوي الثلاثي + المكافأة/المخاطرة بسبعة مكونات) + §25.1-2 (الأنماط الثلاثة: OPTIMISTIC تشخيصي فقط وREALISTIC قبول وSTRESS متانة + تحلل التكلفة السداسي) + §29.1 (سجل التجربة بسبعة عشر حقلاً) + §17.3 (نوافذ الخطر الكلي) + §31.3-5 (decisions/trade_intents/experience_ledger) + §35.3/§51 (ما تحتاجه اللوحة من قرارات).
- جرد الأصول: HardBlockReason الخمسة عشر موجود حرفياً في enums من المرحلة 0 · خريطة دورة الحياة تعرف TRIGGERED→AUTHORIZED/REJECTED_BY_RISK أصلاً (المرحلة 8 تقودهما) · OrderIntent/SlippageRecord/LatencyRecord من §24 جاهزة · ExperienceRecord وعد بشد risk_snapshot في هذه المرحلة («عمداً لا فجوة») · FusionSnapshot يوفر group_scores والإتاحة وveto · ExplainObject يحمل تأجيل التكلفة «المرحلة 8» (وعد يسدد الآن) · location_snapshot يحمل منطقة §10.2 كاملة بدرجات §10.3 · HARD_BLOCK_EVENT_TYPES موطنة في fusion.mapping مع تعليق ينتظر اختبارات المرحلة 8.
- تحديد المعمارية: risk = طبقة قرار (العقد يسمح: scenarios|risk|learning فوق fusion) بسبع وحدات (parameter_sets/no_trade/stop/sizing/costs/engine/store) وlearning = مسار كتابة الدفتر (ledger) — التركيب يبقى في المشغل (verify/الإعادة لاحقاً) لا داخل المحركات.
- القرارات المعمارية (توثق في ADR-026 عند الإغلاق):
  (1) EvaluationContext بحقول افتراضية سليمة — كل حاجب قابل للحقن المستقل حقيقةً واحدة في كل اختبار (بوابة «اختبار حقن فشل مستقل» لكل حاجب).
  (2) تُجمع كل الحواجب المشتعلة لا أول فقط — كل خرق موثق برمزه؛ سبب انتقال الرفض يسمي الأول بترتيب الخطة والعدد الكلي.
  (3) الكتم اللين = مجموع موزون ≥ عتبة إعدادية (§22.2 «بأوزان») وكل كتمة مثبتة بتفسيرها؛ دلالات retry لكل رمز (الصلب بعضه غير قابل لإعادة المحاولة كالقتال الطارئ، واللين كله قابل).
  (4) رفض الحافة الصافية §23.5 أساس ثالث مستقل (NET_EDGE_INSUFFICIENT) خارج أكواد §22 الحرفية؛ ENTRY_TOO_LATE (12) هو متغير التأخر (المكافأة المتبقية بعد التكاليف تحت الحد).
  (5) مرجع الدخول المخطط = الحافة المحافظة للمنطقة (أبعد عن الوقف — أسوأ حالة 1R) وعدم اليقين التنفيذي = كمون × معدل ATR الزمني × مضاعف — كلاهما موثق.
  (6) المعدلات الستة كلها ∈ (0,1] لا ترفع الأحجام أبداً (خاصية «الخطر ≤ السقف»)؛ معدل جودة السيناريو = 1.0 بتأجيل معايرة موثق (§23.2 «after calibration» — المرحلة 9).
  (7) سقوف التحجيم بوحدات الأصل (أداة + محفظة) وسقف نقدي للصفقة — الخاصية تثبت بـ hypothesis على مدخلات عشوائية.
  (8) تحلل §25.2 متطابقة محقاً في النموذج (net = gross − المكونات) وREALISTIC هو نمط القبول وحده.
  (9) شد risk_snapshot إلى RiskDecision نموذجي (وعد المرحلة 0) وسجلات الدفتر صف-لكل-سيناريو (§31.5 حرفياً): MFE/MAE بوحدات R من الدخول المخطط عبر مسار السوق بعد الاشتعال، وأساس P&L الورقي موثق داخل execution_snapshot، وfills/position_path فارغة حتى المرحلة 11.
  (10) هجرة 0008 بثلاثة جداول (decisions §31.3 + trade_intents §31.4 + experience_ledger §31.5) بنمط payload JSONB (ADR-021) ومعرفات uuid5 حتمية وقراءة بجولة واحدة وaudit_risk_gate = البوابة نصاً.
  (11) نوافذ الحظر الكلي من السياق (§17.3) — محرك الكلي مطوي في market_state بنمط انحراف موثق فلا جدول macro_events في MVP.
  (12) تفسير §2.8 لكل قرار بتكلفة مسددة (سداد وعد المرحلة 6) وrejection_reason عند الرفض حصراً.

Stage Summary:
- التصميم جاهز بالكامل والتبعيات محسومة: schemas أولاً ثم المعاملات فالحواجب فالوقف/التحجيم/التكاليف فالمحرك فالدفتر فالهجرة والمخازن فالبوابة.
- البيئة حية من جولة R-6 (بوابات 2175 وverify-phase7 خضراء) — لا استرداد مطلوب، التنفيذ يبدأ فوراً.

---
Task ID: 8-a حتى 8-h (التنفيذ الكامل)
Agent: Main Agent (Z.ai Code — Coordinator)
Task: تنفيذ المرحلة 8 كاملة — لا-تداول + مخاطرة (§22/§23/§25.2/§29.1) وبوابة الخروج

Work Log:
- schemas (8-a): risk.py بعقود المرحلة كلها (MacroEventWindow §17.3 + EvaluationContext بحقول سليمة افتراضياً + NoTradeExplanation §22.3 السداسي + StructuralStop §23.4 + SizingModifier/SizingResult بفرض «الخطر ≤ الميزانية» بنيوياً + CostBreakdown §25.2 بمتطابقة محقاة + RewardRiskEstimate §23.5 السباعي + RiskDecision §31.3 بعقد ترخيص/رفض متبادل) + التعدادات الست (SoftSuppressionReason العشر وNoTradeSeverity وCostMode وRejectionBasis وSizingModifierName وSizingCapBasis) + شد risk_snapshot في ExperienceRecord (وعد المرحلة 0) — 47 مخططاً مصدرة (+9) و131 اختبار نماذج أخضر وmypy نظيف.
- parameter_sets (8-b): RiskConfig بقيود §23.3 العشرة حرفياً وعتبات الحواجب وأوزان الكتمات العشر ومعاملات المعدلات والأنماط ببصمة sha256 — بمدققات اكتمال (الأوزان العشر كاملة والأنماط الثلاثة).
- no_trade (8-c): الحجب الصلب الخمسة عشر بترتيب الخطة مع جمع كل المشتعل + الكتمات العشر بقياسات مشتقة (الموقع من درجات §10.3 والدليل من اللقطة والانجراف والتقلب والأفق) + خريطة دلالات إعادة المحاولة الموثقة لكل رمز — 41 اختباراً منها 19 حقناً مستقلاً (حقيقة واحدة لكل حاجب).
- stop/sizing/costs (8-d): الوقف الثلاثي (بنية ± عازلة ± عدم يقين كموني) بمرجع محافظ · التحجيم بالمعادلة الحرفية والمعدلات الستة (جودة السيناريو محايدة بتأجيل معايرة معلن) وسقف الأحداث يقلص الميزانية · التكاليف بالتحلل السداسي والأنماط (العمولة تعاقدية لا تقيّس) — 16 اختباراً + خاصيتا hypothesis (الخطر ≤ السقف فوق مدخلات عشوائية).
- engine (8-e): RiskEngine بترتيب بوابات حتمي (وقف ← صلب ← لين ← حافة ← تحجيم ← نية وتفسير) — يعيد القرار والحالة الهدف وسبب الانتقال (المشغل يطبق عبر آلة الحياة — عقد الطبقات يمنع استيراد risk←scenarios فاكتُشف أول الرحلة وأعيدت الهيكلة) + التفسير §2.8 بتكلفة مسددة (سداد وعد المرحلة 6) — 15 اختباراً.
- learning (8-f): بناء سجل التجربة عند الإغلاق — MFE/MAE بوحدات R من الدخول المخطط عبر مسار السوق وP&L ورقي موثق الأساس والمرفوض أصفار موثقة لا أرقام مختلقة — 8 اختبارات.
- الهجرة والمخازن (8-g): 0008 بثلاثة جداول (decisions §31.3 + trade_intents §31.4 + experience_ledger §31.5 بصف-لكل-سيناريو فريد) + RiskStore (كتابة idempotent والرفض يمحو النية الراكدة دفاعياً وقراءة بجولة واحدة وaudit_risk_gate = البوابة نصاً: فشل التحقق مخالفة أيضاً) + ExperienceStore في learning — 8 اختبارات تكاملية حية بعد عزل بمناطق فريدة.
- البوابة (8-h): verify_phase8 يستورد مسار المرحلة 7 حرفياً (ScenarioRun + امتداد bar_contexts) ويبني RiskPipeline فوقه: 103 مشتعل ناجٍ ⇒ 103 قرار حتمي (58 ترخيصاً و45 رفضاً) و85 سجل تجربة — 19 فحصاً: العينة والنجاة والقرارات والحقن 15/15 والكتم بحقن القياس (6 كتمات و60 رفضاً موزوناً) والتحجيم والتكاليف والحافة (+0.32 إلى +11.47R وحقن الحد قلب 60) ودورة الحياة (103+40 قانونية) والتفسير المسدد والقانونية والتدهور الآمن والحتمية واللا-نظرة (بادئة 720) وλ=2 (هندسة نسبية ثابتة وانقلابات تكلفة فقط) والقاعدة الحية (idempotent وسجل رفض 45 وجولة واحدة وaudit صفر مخالفين) والدفتر.
- **خللان جوهريان اكتشفتهما أثناء البناء وأصلحهما**: (1) قراءة سقف الفاتحة الضيقة جعلت كل سكالب بوقف رشيق (0.75 ATR) مستحيلاً — أوسح الحدين (الأساسان البديلان في نص §22.1-4) والتقديرات صارت بمقياس ATR (ADR-015) بدل مطلق ينفك عن مقياس الإطار. (2) خريطة §18.2 تمنع AUTHORIZED→EXPIRED (الانقضاء نافذة ترخيص) — نهاية المُرخَّص بالإبطال/إلغاء الجودة حصراً.
- البوابات النهائية: make gate = 2294 (+119) وintegration 46 (+8) وschemas check 47 وverify-phase7 أعيد إثباته (18 أخضر بعد امتداد مشغله) وverify-phase8 = 19 أخضر.

Stage Summary:
- **بوابة المرحلة 8 مغلقة رسمياً**: «كل خرق مخاطرة = رفض صلب موثق بكود» محققة بالحقن الشامل 15/15 على مشتعل حقيقي + audit_risk_gate صفر مخالفين على القاعدة الحية — والمحرك يثبت نفسه على بيانات حقيقية بمساره كاملاً (اشتعال ← تقييم ← ترخيص/رفض ← نهاية موثقة ← دفتر).
- **الحصيلة**: حزمة risk (سبع وحدات) + learning (ledger/store) + هجرة 0008 + 47 مخططاً + 2294 اختباراً + ADR-026 (أحد عشر قراراً).
- **التالي بحسب الخطة**: المرحلة 9 — الإعادة والوسم والاختبارات العكسية (§26: مشغل إعادة event-time بلا تسريب وsimulated execution بالتكاليف والوسم §30 والمقاييس §29.2 وأدوات WFO §39.3 وحتمية §26.2) — مدخلها قرارات المخاطرة وسجلات التجارب الجاهزة الآن بصورتها النهائية.

---
Task ID: R-7 (جولة تحقق + استرداد)
Agent: Main Agent (Z.ai Code — Coordinator)
Task: التحقق من التقدم بحسب الخطة والحالة الحالية وتحديد المرحلة التالية (طلب المستخدم) — تضمن استرداد البيئة المحية

Work Log:
- تحقق Git: المحلي = البعيد عند ab9a27c (بوابة المرحلة 8) — الوسوم الستة موسومة ومرفوعة كلها (phase-4/5a/6/7/8-gate) — 209 تغييرات معلقة كلها ضجيج (إدخال arrival-log واحد + mode-only + tool-results) نُظفت بـ reset --hard — شجرة نظيفة.
- الحسم التاريخي: المراحل 0-8 كلها مغلقة رسمياً ومرفوعة وموثقة — المرحلة 8 (ab9a27c + وسم phase-8-gate): لا-تداول ومخاطرة كاملة (الحجب 15 بحقن مستقل والكتم الموزون ووحدة R بمعدلاتها الستة والوقف البنيوي والتكاليف §25.2 والدفتر §29.1 وهجرة 0008) بموثقة progress.md وADR-026.
- محو المنصة مجدداً (R-7 — النمط السابع): venv و.env والثنائيات ضائعة والخدمات كلها متوقفة — الاسترداد المعتاد: uv sync --all-packages ثم .env من المثال ثم make infra-provision ثم إطلاق الغلافين double-fork.
- الصحة بعد الاسترداد: supervisor status كله سليم (postgres HEALTHY + nats HEALTHY + seaweedfs HEALTHY + migrate EXITED_OK + worker HEALTHY) + engine-api healthz 200 (uvicorn على 4001) + alembic عند 0008_risk_tables (الرأس).
- إعادة إثبات البوابات على البيئة المستردة: make gate = 2294 passed + verify-phase8 = 19 فحصاً أخضر + verify-phase7 = 18 فحصاً أخضر + integration = 46 passed — كلها مطابقة لأرقام إغلاق المرحلة 8 حرفياً (103 قرارات حقيقية و58 ترخيصاً وحقن 15/15 و85 سجل تجربة).
- قراءة قسم D من build_plan.md: المرحلة التالية هي 9 — الإعادة والوسم والاختبارات العكسية (9.1 مشغل الإعادة event-time بنافذة قراءة متحركة §26.3 وseed §26.2 · 9.2 محاكاة التنفيذ بالأنماط الثلاثة وتعبئة جزئية بنتائج golden · 9.3 محرك الوسم §30 بالحالات الخمس والترتيب المتحفظ · 9.4 المقاييس (توقع صافي وعامل ربح وتوزيع R وMFE/MAE) · 9.5 أدوات WFO §39.3 (2000/500/500 خطوة 500) · 9.6 حتمية الإعادة اختبار CI-مستمر) وبوابة خروجها: إعادة كاملة آلية موثقة وصفر تسريب في فحوص §26.3 الستة.
- ملحوظة بنية: التطبيق engine/apps/replay موجود منذ المرحلة 5a (الاستئصال) — المرحلة 9 ستبني عليه/توسعه بحسب العقد.

Stage Summary:
- الحالة مؤكدة بالكامل: المراحل 0-8 مغلقة (8 بوابات موسومة: 0-8) والبيئة حية مستردة والبوابات مثبتة عليها خضراء (2294 + 19 + 18 + 46) — لا انحراف بين المحلي والبعيد والوثائق.
- المرحلة التالية بحسب الخطة: المرحلة 9 (الإعادة والوسم والاختبارات العكسية) — مدخلاتها قرارات المخاطرة وسجلات التجارب الجاهزة من المرحلة 8 بصورتها النهائية الموثقة.
- لم تُكتب أي شيفرة جديدة في هذه الجولة (طلب تحقق) — لا التزام جديد مطلوب (الشجرة نظيفة عند رأس البعيد).

---
Task ID: 9-0
Agent: Main Agent (Z.ai Code — Coordinator)
Task: قراءة مواصفات المرحلة 9 كاملة (الإعادة والوسم والاختبارات العكسية) وتصميم معمارية الإعادة والمحاكاة والوسم والمقاييس وWFO

Work Log:
- قراءة §26 كاملاً (المبادئ الثمانية: event-time ولا بيانات-مستقبل ونفس دوال السمات حياً وإعادةً وتكاليف وكمون وتعبئة جزئية وفجوات محفوظة وإصدارات معاملات جامدة + §26.2 الاستنساخ: المعرّفات التسعة backtest_id/data_snapshot_id/code_version/model_version/parameter_set_version/cost_model_version/random_seed/start_time/end_time/instrument_set والنتيجة الدقيقة قابلة للاستنساخ منها + §26.3 كشف اللا-نظرة الستة) + §30 (الحالات الخمس TARGET_FIRST/INVALIDATION_FIRST/TIMEOUT_WITH_PROFIT/TIMEOUT_WITH_LOSS/NOT_EXECUTABLE والترتيب المتحفظ داخل الشمعة «يجب ألا يختار المخرج المحابي أبداً لمجرد جمال الإعادة») + §29.2 (MFE/MAE من مسار الدخول الفعلي) + §39.3 (WFO: 2000 تدريب/500 تحقق/500 خارج-العينة تتدحرج 500 مرتبة زمنياً مع حجز ≥ أقصى أفق تقييم — «لا تُقلص الأعداد لمجرد عبور بوابة») + §31.4/31.5 (لا جدول backtests في النموذج الأدنى — التقرير مصنوع الحصيلة) + §28 («الإعادة القانونية للقبول تعمل في محرك الإعادة الخارجي»).
- جرد الأصول: حزمة engine-backtest موجودة كهيكل فارغ منذ المرحلة 0 بموقعها الصحيح في عقد الطبقات (تحت الكواشف — تستورد schemas/common/quantmath/features فقط) + engine_replay هيكل CLI بوعد موثق «المحرك الفعلي يُبنى في المرحلة 9» + علامة pytest «replay» معدة منذ المرحلة 0 بلا اختبارات بعد + ablation بنقطة حقن MetricEvaluator معلقة على المرحلة 9 + ScenarioRun (verify_phase7) وRiskPipeline (verify_phase8) هما التركيب المثبت الحتمي (سلسلة السكربتات: 8 استورد من 7 — 9 يستورد من كليهما).
- تحديد المعمارية (عقد الطبقات يحكمها):
  (1) packages/backtest = مكتبة الميكانيكا الصرفة: window (نافذة القراءة المتحركة §26.3 — رؤية الشموع المغلقة حصراً bar_time+tf ≤ as_of والأحداث event_time ≤ as_of — المنع المعماري لا التزاماً) + identity (المعرفات التسعة uuid5) + execution (محاكي تعبئة حتمي: وصول الشمعة التالية + كمون، تعبئة عند الحافة المعاكسة تحفظاً، تعبئة جزئية بنسبة إعدادية، عكسي-أولاً داخل الشمعة: الوقف قبل الهدف عند لمسهما معاً والدخول ثم الوقف عند اقترانهما — لا مخرج محابٍ أبداً) + costs (تحلل §25.2 السداسي المحقق على التعبئات الفعلية بالأنماط الثلاثة وREALISTIC نمط القبول) + labeling (§30 الخمس بالترتيب المتحفظ) + metrics (توقع صافٍ وعامل ربح وتوزيع R وMFE/MAE وحسب النظام) + wfo (بروتوكول §39.3 مع حجز وامتناع موثق عند نقص المرشحين) + report (تجميع حتمي بايت-بايت).
  (2) schemas/backtest.py = العقود العابرة للطبقات (SimulatedFill/SimulatedTrade/RealizedCosts/LabelResult/BacktestMetrics/RegimeMetrics/BacktestIdentity/WFOWindow/WFOReport/BacktestReport) + تعدادات LabelState وExitReason وWFORole وIntrabarPolicy — مصدرة إلى generated.
  (3) engine_replay = خط أنابيب الميكانيكا القابل لإعادة الاستخدام (شموع + نوايا → تعبئات → وسم → مقاييس → تقرير) وأوامر CLI فعلية (backtest/wfo) — وفاء وعد «المحرك الفعلي يُبنى في المرحلة 9».
  (4) التركيب الكامل (سيناريو+مخاطرة+تنفيذ محاكى) يقود في سلسلة السكربتات: verify_phase9 يستورد ScenarioRun وRiskPipeline من 7/8 (نمط 8→7 الحرفي — لا جراحة على بوابات مثبتة).
- القرارات الموثقة (تدون في ADR-027 عند الإغلاق):
  (1) لا هجرة قاعدة بيانات في المرحلة 9 — §31 لا يعدّ جدول backtests في النموذج الأدنى و§26.2 يجعل التقرير قابلاً للاستنساخ من المعرّفات ذاتها؛ الحصيلة ملفات تقارير حتمية موثقة (نمط engine/docs/ablation/phase5a).
  (2) التعبئة التحفظية حرفية: داخل الشمعة الواحدة العكس يُفحص أولاً دائماً — target+stop معاً ⇒ INVALIDATION_FIRST حتماً؛ الدخول والوقف في شمعة واحدة ⇒ دخول ثم وقف (أسوأ حالة) — IntrabarPolicy تعداد بCONSERVATIVE وحده في MVP وHIGHER_RESOLUTION مؤجل موثق.
  (3) عامل الربح بلا خاسرين = None معلن (لا اختلاق ∞)؛ والتوقع الصافي بوحدات R الصافية بعد تكاليف REALISTIC.
  (4) العينة الحقيقية (103 قرارات) لا تكفي بروتوكول §39.3 (3000 مرشح) — الفاحص الآلي يثبت البروتوكول الكامل على 3000 اصطناعي حتمي + يولد تقارير قابلة لإعادة الإنتاج على العينة ببروتوكول بنية معلن SAMPLE_STRUCTURE (لا يُدّعى عبور بوابة بحث) — «الأعداد لا تُقلص لمجرد عبور بوابة».
  (5) فحوص §26.3 الستة فحوص صريحة مسماة في البوابة (فهرسة/تأكيد سوينغ/صف فوتبرنت/مراقبة كلية منقحة قبل الإصدار/سمات ما بعد الدخول/لا معايرة على طية التقييم).
  (6) حتمية CI-مستمر (9.6): tests/replay/test_replay_determinism.py على عقد صناعي صغير ملتزم — نفس المعرّفات ⇒ تقرير متطابق بايت-بايت في كل make gate؛ والحتمية الكاملة للمسار الحقيقي فحص البوابة (تشغيلان متطابقان).

Stage Summary:
- التصميم جاهز والتبعيات محسومة: schemas أولاً ثم مكتبة backtest (ثماني وحدات) ثم خط أنابيب engine_replay ثم الاختبارات ثم البوابة verify_phase9 بسلاسل الاستيراد الموروثة.
- البيئة حية من جولة R-7 (بوابات 2294/19/18/46 خضراء) — التنفيذ يبدأ فوراً.

---
Task ID: 9-a حتى 9-h (التنفيذ الكامل) + الإغلاق
Agent: Main Agent (Z.ai Code — Coordinator)
Task: تنفيذ المرحلة 9 كاملة — الإعادة والوسم والاختبارات العكسية (§26/§30/§29.2/§39.3) وبوابة الخروج

Work Log:
- schemas (9-a): backtest.py بعقود المرحلة كلها (SimulatedFill/SimulatedTrade بمتطابقة تعبئات-كمية وRealizedCosts بتحلل §25.2 المحقق المحقاة وEntrySpec بمواصفة ما يراه المحاكي حصرًا وRDistribution/RegimeMetrics/BacktestMetrics وBacktestIdentity بالمعرفات التسع وWFOSegment/Window/ProtocolConfig/Report وBacktestReport بقبول REALISTIC وCONSERVATIVE حصرًا) + التعدادات الأربعة (LabelState الخمس وExitReason الخمسة وWFORole وIntrabarPolicy) — 60 مخططاً مصدرة (+13) وعامل الربح NonNegativeFloat|None (الصفر قانوني — خلل اكتشفته الاختبارات).
- مكتبة backtest (9-b..9-f): parameter_sets (BacktestConfig بجداول التكلفة الثلاثة وبصمة sha256 وبروتوكول بنية العينة معلن الاسم) · window (النافذة المعمارية: مغلقة حصرًا وأحداث بلحظتها وعقرب زمني حصرًا وتدقيق audit) · identity (ختم uuid5) · execution (المنفّذ: حافة معاكسة وتعبئة جزئية بنسبة إعدادية وزمن حدث عند الإغلاق وشريط مهلة عابر بفرضية الضرر ولا هدف بعد المهلة) · costs (تحلل محقق واحد بلا ازدواج) · labeling (الخمس بالترتيب المتحفظ) · metrics (توقع/عامل ربح/توزيع/MFE-MAE حسب النظام بغياب معلن) · wfo (بحث 2000/500/500 حرفيًا بحجز زمني ورفض صاخب عند النقص) · report (بنّاء مختوم بساعة قابلة للحقن).
- engine_replay (9-b): خط أنابيب run_backtest (ترتيب حتمي + نافذة + منفّذ + تقرير) وأوامر CLI فعلية backtest/wfo — وفاء وعد «المحرك الفعلي يُبنى في المرحلة 9».
- الاختبارات: 62 وحدة جديدة في سبعة ملفات (ذهبي محسوب يدويًا وتحفظ الاتجاهين وحالات المهلة والعابر والبيانات-الأقصر وحتمية بايت-بايت وWFO بحث كامل على 5000 اصطناعي) + 5 اختبارات replay بعلامة مستمرة (CI-مستمر 9.6).
- البوابة (9-g): verify_phase9 بسلسلة الاستيراد الموروثة (7→8→9 — لا جراحة على بوابات مثبتة): ReplayPipeline فوق ScenarioRun وRiskPipeline حرفياً ثم العالم المحاكى — 18 فحصاً: العينة والمسار الكامل (58⇒58⇒58) والذهبي المرجعي والتحفظ (صفر غموض في العينة) والوسم الخمس متسقة والتعبئة الجزئية لا تتجاوز والأنماط الثلاثة مرتبة والمقاييع معاد اشتقاقها وفحوص §26.3 الستة صفر تسريب (فهرسة/سوينغ/فوتبرنت/كلية/سمات/معايرة-طيات) والحتمية الكاملة بايت-بايت وλ=2 (هندسة نسبية ثابتة ولا انقلاب ضار) وWFO عينة (7 نوافذ قابلة لإعادة الإنتاج) والحصيلة الموثقة والقانونية.
- خللان جوهريان اكتشفتهما أثناء البناء وأصلحهما: (1) عامل الربح صفراً (مجموعة كلها خاسرة) كان يرفضه العقد PositiveFloat — الصفر معنى قانوني فأصبح NonNegativeFloat. (2) عند λ=2 مررت مسار المنفّذ بشموع غير مقيسة بينما المحرك يقيس داخلياً — فصارت كل المناطق فوق الشموع ولا لمس (73/73 UNFILLED)؛ الحل: مسار التنفيذ بscaled_klines ذاتها — البوابة هي التي كشفته.
- الإغلاق (9-h): ADR-027 (أحد عشر قراراً) + قسم المرحلة 9 في progress.md وسطر الجلسة ومزامنة engine/docs + الحصيلة docs/backtest/phase9 (تقرير الإعادة بختم الهوية وتقرير WFO).
- البوابات النهائية: make gate = 2361 (+67) وintegration 46 وschemas check 60 وverify-phase7 أعيد إثباته (18) وverify-phase8 أعيد إثباته (19) وverify-phase9 = 18 أخضر.

Stage Summary:
- **بوابة المرحلة 9 مغلقة رسمياً**: «إعادة كاملة آلية موثقة؛ صفر تسريب مكتشف في فحوص §26.3 الستة» محققتان — التقرير حصيلة موثقة بختم هوية §26.2 قابلة للاستنساخ من معرفاتها، والستة فحوص صريحة خضراء على مسار حقيقي كامل (اشتعال ← تقييم ← ترخيص ← محاكاة ← وسم ← مقاييس).
- **نتيجة القياس الأولى الصادقة**: على عينة يوم واحد (58 صفقة محاكاة REALISTIC تحفظية): التوقع الصافي −0.967R وعامل الربح 0.36 ومعدل الفوز 22% — النظام يقيس بصدق لا يجمل (هذا عمل الإعادة؛ المعايرة والتدريب مختبر التعلم بعد MVP).
- **الحصيلة**: مكتبة backtest (تسع وحدات) + engine_replay بخط أنابيب وCLI + 60 مخططاً + 2361 اختباراً + حصيلة موثقة + ADR-027.
- **التالي بحسب الخطة**: المرحلة 10 — TradingView + اللوحة الدنيا (10.1 مكتبة Pine §27.1/27.2 · 10.2 المؤشر بطبقات العرض §35.1 · 10.3 webhook D-09 بمتطلبات §36 · 10.4 المرآة الحتمية D-08 · 10.5 اللوحة الدنيا §35.2/35.3 عبر XTransformPort=4001) — وبوابتها MVP-DoD بقائمة §51 بنداً بنداً.

---
Task ID: R-8
Agent: Main Agent (Z.ai Code — Coordinator)
Task: جولة تحقق شاملة — تأكيد إغلاق المراحل 0-9 واسترداد البيئة (النمط الثامن) وإعادة إثبات البوابات وتحديد المرحلة التالية

Work Log:
- تحقق Git: المحلي = البعيد عند e8f03af (بوابة المرحلة 9 — الإعادة والوسم والاختبارات العكسية) — الوسم phase-9-gate موسوم ومرفوع — 245 تغييراً معلقاً كلها ضجيج (244 mode-only + إدخال arrival-log واحد) نُظفت بـ reset --hard — شجرة نظيفة.
- الحسم التاريخي: المراحل 0-9 كلها مغلقة رسمياً ومرفوعة وموثقة — المرحلة 9 (e8f03af + وسم phase-9-gate): مكتبة backtest التسع وحدات (نافذة §26.3 معمارية + معرفات §26.2 + منفذ بذهبي مرجعي + تكاليف محققة + وسم §30 متحفظ + مقاييس §29.2 + WFO §39.3 + تقرير مختوم) وengine_replay بخط أنابيب وCLI فعلية و18 فحص بوابة وصفر تسريب §26.3 وADR-027 وحصيلة docs/backtest/phase9.
- محو المنصة مجدداً (R-8 — النمط الثامن): engine/.venv محية (uv أنشأ فارغة بلا yaml) و.env ضائع والثنائيات ضائعة وكل الخدمات متوقفة — الاسترداد المعتاد: unset VIRTUAL_ENV ثم uv sync --all-packages (استغرق ~13 دقيقة لبطء الشبكة — نُفذ بخلفية مراقبة بعد نفاد مهلتَي 300s/600s لأن الخلفية المنفصلة تُقتل بانتهاء الأمر) ثم .env من المثال ثم make infra-provision ثم إطلاق الغلافين double-fork.
- الصحة بعد الاسترداد: supervisor كله سليم (postgres HEALTHY + nats HEALTHY + seaweedfs HEALTHY + migrate EXITED_OK + worker HEALTHY) + engine-api healthz 200 على 4001.
- إعادة إثبات البوابات على البيئة المستردة: make gate كامل المراحل (lint: 244 ملفاً منسقاً + ruff كل الفحوص + mypy strict: 219 ملفاً بلا مشاكل + imports: 6 عقود محفوظة + test: 2361 passed) — وverify-phase9 = 18 فحصاً أخضر (بما فيها فحوص §26.3 الستة صفر تسريب والحتمية بايت-بايت) — وverify-phase8 = 19 فحصاً أخضر — وverify-phase7 = 18 فحصاً أخضر — وintegration = 46 passed — كلها مطابقة لأرقام إغلاق المرحلة 9 حرفياً.
- قراءة قسم D من build_plan.md: المرحلة التالية هي 10 — TradingView + اللوحة الدنيا (10.1 مكتبة Pine §27.1/27.2 · 10.2 المؤشر بطبقات العرض السبع §35.1 · 10.3 webhook D-09 بمتطلبات §36 الثمانية + D-07 · 10.4 المرآة الحتمية D-08 · 10.5 اللوحة الدنيا §35.2/35.3 عبر XTransformPort=4001) وبوابتها: MVP-DoD بقائمة §51 بنداً بنداً + تفتيش صفقة/سيناريو كامل السلسلة + make gate أخضر شامل + اللوحة تعرض بيانات فعلية.
- بعد MVP خارطة معلنة: 11 محول التنفيذ (testnet) ثم 12 مختبر التعلم ثم 13 المباشر المتحكَّم (5b الهارمونيك مؤجل).

Stage Summary:
- الحالة مؤكدة بالكامل: المراحل 0-9 مغلقة (9 بوابات موسومة مرفوعة: phase-4/5a/6/7/8/9-gate) والبيئة حية مستردة والبوابات كلها مثبتة عليها خضراء (gate 2361 + phase9 18 + phase8 19 + phase7 18 + integration 46) — لا انحراف بين المحلي والبعيد والوثائق.
- المرحلة التالية بحسب الخطة: المرحلة 10 (TradingView + اللوحة الدنيا) — بوابتها MVP-DoD §51 وهي آخر مرحلة MVP — مدخلاتها كل مخرجات 0-9 الحية (الاستدلال والمخاطرة والإعادة الموثقة).
- لم تُكتب أي شيفرة جديدة في هذه الجولة (طلب تحقق) — لا التزام جديد مطلوب (الشجرة نظيفة عند رأس البعيد عدا إدخال worklog هذا).


---
Task ID: 10-0
Agent: Main Agent (Z.ai Code — Coordinator)
Task: قراءة مواصفات المرحلة 10 كاملة (TradingView + اللوحة الدنيا — بوابة MVP-DoD) وتصميم المعمارية

Work Log:
- قراءة المواصفات الأم كاملة: §27.1 (حالات الإشارة الأربع DEVELOPING/CONFIRMED/INVALIDATED/RETRACTED — المؤكدة وحدها تؤهل القرار والقابلة للتطور عرضية حصرًا) + §27.2 (HTF بقيم مؤكدة حصرًا — تقنيات القيمة المؤكدة ضد الرفرفة) + §27.4 (التنبيهات القادرة على الأوامر الحية من منطق مؤكد حصرًا) + §35.1 (طبقات العرض السبع بترتيبها: خريطة السيولة الكبرى فنطاق المعالجة فبنية HTF/MTF فالسيناريو النشط فالدخول/الإبطال/الأهداف فتعليقات التدفق المختارة فعلامات الأحداث — «لا رسم كل شيء») + §35.2 (اللوحة الدنيا بثلاثة عشر حقلًا) + §35.3 (أثر الاستدلال القابل للطي: لماذا نشط/ماذا ضده/لماذا الانتظار — أثمن من ملصق BUY 91%) + §36 (بروتوكول webhook بحمولة §36 المثالية وخطوات الخدمة الثمانية: مصادقة فتحقق مخطط ففحص تكرار idempotency_key فحفظ الخام فإقرار فوري فنشر NATS فإعادة تحقق المحرك القانوني فحينئذ فقط مخاطرة/تنفيذ) + §6.4 (حدود webhook: إقرار <3s والعمل الثقيل غير متزامن ولا أسرار في الجسم) + §31.6 (جدول alerts تشغيلي) + §51 (قائمة MVP الستة عشر بندًا) + خروج المرحلة 10 من Master Plan (الاتفاق ضمن التسامح المعلن على المجموعة المشتركة من الحسابات).
- قراءة قرارات plan_review: D-07 (idempotency = sha256(schema_version|source|alert_id|instrument|bar_time|event) — حتمي مخزن مع الخام) + D-08 (جدول تسامح لكل عائلة: OHLCV تامة، ATR ±0.01%، دلتا/POC ±0.5% مع تعليق اختلاف المصدر منهجيًا موثقًا لا فشلًا، الأحداث البنائية BOS/Sweep مطابقة صارمة عند تساوي الإصدارات والمعايير) + D-09 (مسار /api/tv/webhook في Next الحافة العامة يمرر إلى FastAPI داخليًا عبر نمط المنصة XTransformPort) + ملحوظة TV غير-بريميوم (البوابة على المجموعة المشتركة المتاحة فقط).
- جرد الأصول: TV_WEBHOOK_SECRET موجود في Settings منذ المرحلة 0 + Caddyfile يؤكد توجيه ?XTransformPort=4001 + apps/api هيكل healthz فقط (وعده «webhook، حالة، سيناريوهات» يُفى الآن) + كل الخدمات مستوردة في venv بلا حقن مسارات (uv sync --all-packages) + سلسلة التوليف المثبتة: verify_phase7.ScenarioRun (559 مقترحًا/105 اشتعالات) وverify_phase8.RiskPipeline (103 قرارات/58 ترخيصًا/45 رفضًا) وverify_phase9.ReplayPipeline (58 صفقة) — جميعها فوق عينة PHASE2_DIR الثلاثية الأطر (1m/15m/1h) في المستودع.
- قراءة رياضيات المرآة المطلوبة حرفيًا: wilder_atr (بذرة SMA عند period-1 فاستدعاء ذاتي — مطابق لـta.rma في Pine) + قاعدة المتطرفات الفراكتلية (حافة دخول شمعتين + تأكيد متأخر confirm_bars وإبطال بالأعلى) + آلة الاجتياح (لمس فتغلغل وعتبة max(0.25×ATR، 0.5×عرض) فنافذة 3 بقبول إغلاقين أو استرجاع أو انقضاء) + عتبات ADR-015 (STRUCTURAL_LEVEL_BUFFER=0.5/DISPLACEMENT_MIN=1.0/SWEEP_TOLERANCE=0.25 مضاعفات ATR فترة 14) + BOS (مرجع الإغلاق الأقرب فاختراق العتبة فابتلاع المستويات الأضعف + مسار الفتيل المفعّل) + مغلف §32 والعقود المصدرة (60 مخططًا).
- المعمارية المثبتة (عقد الطبقات يحكمها — apps > decisions > fusion > detectors > context > backtest > features > foundations):
  (1) schemas أولاً: tv.py (TVAlertPayload §36 بلا أسرار + TVAlertEnvelope بعقلية §32 للناقل + AlertDeliveryStatus/AlertRevalidation/WebhookAck) + dashboard.py (لوحة §35.2 بثلاثة عشر حقلًا + ReasoningTraceView §35.3 + ScenarioView/RejectionView/ExecutionView/WebhookEventView/DashboardOverview) — تصدَّر إلى generated.
  (2) pine/ في جذر المستودع: libraries/engine_core.pine (حالات الإشارة §27.1 + قارئ HTF المؤكد §27.2 + ATR وايلدر + المتطرفات الفراكتلية + آلة الاجتياح + BOS — نفس معادلات المحرك حرفيًا) + indicators/reasoning_engine.pine (الطبقات السبع §35.1 بترتيبها وتحكم انتقائي) + alerts/ (توثيق التنبيه: التوكن في الرابط لا المصدر §37.1).
  (3) المرآة 10.4: engine_replay/mirror.py — نسخ بايثوني مستقل من مصدر Pine (كتب بإعادة قراءة المصدر لا بنسخ المحرك) يقارن بمحركات الخدمة فوق عينة phase2: OHLCV تامًا وATR ±0.01% وSweep/BOS صارمًا على المجموعة المشتركة (خريطة السيولة الكبرى المرسَّمة من المتطرفات الخارجية — مناطق القمم/قيعان الجلسة إثراء جانب-المحرك موثق) وصف دلتا/POC «غير مشترك» موثقًا (حساب TV غير بريميوم §6.2) — حصيلة docs/mirror/phase10/mirror_report.json + أداة فحص بنية مصدر Pine.
  (4) webhook 10.3: جدول alerts بهجرة 0009 (§31.6) + مسار FastAPI POST /api/tv/webhook بالخطوات الثماني (توكن في الاستعلام مقارنة زمنية ثابتة — التوكن لا يوضع في مصدر Pine أبدًا + تحقق مخطط + مفتاح D-07 يحسبه الخادم حصرًا لا يثق بمفتاح وافد + فحص التكرار بقيد فريد = إقرار DUPLICATE بلا معالجة ثانية + حفظ الخام + إقرار فوري + نشر NATS tv.alert.received بمغلف TVAlertEnvelope + إعادة تحقق خلفية مقابل التوليف القانوني وقرار مخاطرة موثق — التنفيذ الحقيقي مؤجل للمرحلة 11 معلنًا) + مسار Next /api/tv/webhook يمرر عبر XTransformPort=4001 (الأصل من ترويسة host — لا منفذ مكتوب في الشيفرة).
  (5) اللوحة 10.5: composition.py في apps/api يعيد استخدام ScenarioRun وRiskPipeline حرفيًا (استيراد من scripts بحقن مسار موثق — نفس كائنات البوابات لا نسخة ثانية: اللوحة تعرض أرقام البوابات نفسها 103/58/45/58) + مسارا قراءة /api/dashboard/overview و/api/dashboard/alerts + صفحة Next الوحيدة / بتبويبات (السوق/السيناريوهات النشطة/أثر الاستدلال/سجل الرفض/التنفيذ والتنبيهات) تجلب عبر ?XTransformPort=4001.
  (6) بوابة الخروج: verify_phase10 بقائمة §51 بندًا بندًا (كل بند بأمر تحقيقه من verify_phase1..9/10) + تفتيش سيناريو/صفقة كامل السلسلة + مطابقة أرقام اللوحة مع أرقام البوابات الموثقة + فحوص webhook الثمانية (مكرر/فاسد/غير موثق = رفض صحيح) + مرآة D-08 + E2E بالوكيل الآلي (تحميل وبيانات فعلية ولا تحذيرات وحدة تحكم) + make gate أخضر.
- القرارات التي ستدون في ADR-028: (أ) مفتاح idempotency يحسبه الخادم حصرًا (D-07 فوق حقول الخام الخمسة — لا ثقة بمفتاح وافد) (ب) التوكن في معامل الاستعلام لا الترويسة (TV لا يضبط ترويسات مخصصة) ولا في مصدر Pine أبدًا (§37.1) (ج) إعادة استخدام توليفات البوابات من scripts حرفيًا في apps/api — اللوحة والبوابات كائن واحد لا نسختان (د) نطاق المرآة = المجموعة المشتركة المتاحة (سيولة كبرى مرسَّمة من المتطرفات + ATR + BOS + Sweep؛ دلتا/POC غير مشترك موثق) (هـ) إعادة تحقق webhook تنتهي عند قرار المخاطرة الموثق — لا أمر حي في MVP (المرحلة 11) (و) لا جدول سيناريوهات جديد — اللوحة تقرأ من الحصيلة المثبتة والتوليف الحتمي.

Stage Summary:
- التصميم مكتمل والتبعيات محسومة: schemas أولاً ثم pine ثم المرآة ثم الهجرة والwebhook ثم composition واللوحة ثم البوابة بفحوص §51.
- البيئة حية من R-9 (gate 2361 + phase9 18 + integration 46) — التنفيذ يبدأ فورًا بالترتيب أعلاه.


---
Task ID: 10-a حتى 10-h (التنفيذ الكامل) + الإغلاق
Agent: Main Agent (Z.ai Code — Coordinator)
Task: تنفيذ المرحلة 10 كاملة — TradingView + اللوحة الدنيا وإغلاق بوابة MVP-DoD §51

Work Log:
- الاسترداد R-9 (النمط التاسع): amend ضجيجي بعد دفع R-8 نُظف بـ reset --hard إلى origin/main (الفرق ضجيج صرف مؤكد: arrival-log وnode-watcher.pid و244 mode-only) + venv محية فأعيد بناؤها (الكاش دافئ فاكتملت في ثوانٍ) + .env من المثال + make infra-provision + الغلافان double-fork + إعادة إثبات البوابات قبل البدء (gate 2361 وverify-phase9 18 وintegration 46).
- schemas أولاً (10-a): tv.py (TVAlertPayload بلا idempotency_key عمدًا — D-07 يشتقه الخادم حصرًا + TVAlertEnvelope بعقلية §32 + AlertDeliveryStatus الست + AlertRevalidation + WebhookAck) وdashboard.py (PanelField وReasoningTraceView §35.3 الثلاثة أقسام وScenarioView وRejectionView وExecutionView بوضع SIMULATION_ONLY المعلن وWebhookEventView وDashboardCounts وDashboardOverview) — 12 مخططًا جديدًا (72 إجمالًا) كلها مصدرة ومتحقق منها بايت-بايت.
- pine (10-b و10-c): المكتبة engine_core.pine (حالات الإشارة §27.1 وقارئ HTF المؤكد §27.2 بتقنية [1]+lookahead_on وATR وايلدر خام f_atrWilder ومحدود الذاكرة f_atrBounded بسياسة المحرك (مخزن دائري 114) والقطبية الصحيحة قمة⇒BUY_SIDE والمعرف التسلسلي الفريد للمناطق وآلة الاجتياح §10.4 بحالاتها الأربع وكسر البنية §11.2-3 بحادثَي الاتجاهين وباني حمولة §36 الثمانية بلا أسرار) والمؤشر reasoning_engine.pine (الطبقات السبع §35.1 بترتيبها بتحكم انتقائي والإسقاط الهندسي للسيناريو والإسقاط باتجاه صحيح: اجتياح القمم ورفضها هابط) وREADME التوثيقي وalerts/README (التوكن في الرابط لا المصدر §37.1).
- المرآة D-08 (10-d): engine_replay/mirror.py — منافذ بايثونية مستقلة كتبت بإعادة قراءة مصدر Pine (لا بنسخ المحرك) قوبلت بمكونات المحرك الحقيقية بترتيب الواجهات الموثق. العملية كشفت وأصلحت أربعة أخطاء ترجمة حقيقية: (1) قطبية المناطق معكوسة (المحرك: قمة⇒BUY_SIDE فوق السعر) (2) معرف المنطقة بفهرس الشمعة يتصادم عند تأكيد قمة وقاع بنفس الشمعة فيفسد ربط التفاعلات — معرف تسلسلي فريد (3) ATR: المحرك سياسة مخزن دائري محدود الذاكرة لا RMA متراكمة (انحراف 0.054% يقلب قرارات) (4) المساواة ليست عبورًا في اختيار مستوى الكسر (عقد _nearest_level). النتيجة النهائية: OHLCV تامة وATR ±4.23e-7 وSWINGS 366/366 وSWEEP 255/255 وBOS 74/74 صارمة وDELTA_POC موثق غير مشترك (فوتبرنت TV يتطلب Premium §6.2) — AGREED_WITHIN_TOLERANCE + حصيلة docs/mirror/phase10/mirror_report.json قابلة لإعادة الإنتاج بايت-بايت + أمر CLI ‎engine-replay mirror + أداة فحص بنيوي لمصدر Pine (صفر خرق).
- الويبهوك (10-e): هجرة 0009_tv_alerts (جدول alerts §31.6: الجسم الخام JSONB والحالة والنتيجة والقيد الفريد على مفتاح D-07) + settings_bridge (مجموعة اتصال asyncpg بدورة حياة) + api/webhook.py بالخطوات الثماني: مصادقة بالتوكن في الاستعلام بمقارنة زمنية ثابتة (401 عند الغياب/الخطأ) + تحقق مخطط (422 للفاسد) + مفتاح D-07 المشتق خادميًا فوق الحقول الخمسة + فحص التكرار بقيد فريد (إقرار DUPLICATE بلا معالجة ثانية — ثبت عمليًا عبر المسارين معًا) + حفظ الخام بايت-بايت + إقرار فوري 7ms (مقابل حد 3s §6.4) + نشر NATS tv.alert.received بمغلف TVAlertEnvelope + إعادة تحقق قانونية خلفية (to_thread كي لا تسد الحلقة + تسخير عند الإقلاع) توثق PROCESSED/REJECTED_CANONICAL ولا أمر حي في MVP + مسار حافة Next /api/tv/webhook يمرر عبر نمط المنصة (الأصل من ترويسة الطلب — لا منفذ مكتوب في الشيفرة).
- اللوحة (10-f): composition.py يعيد استخدام ScenarioRun وRiskPipeline حرفيًا من سكربتات البوابات (حقن مسار موثق ADR-028 — كائن واحد لا نسختان: فحص البوابة يثبت 103/58/45/58 حرفيًا) + لوحة §35.2 بثلاثة عشر حقلًا بمعرفات النص وترتيبه (السيولة فوق/تحت سطر واحد) + أثر §35.3 من تفسير §2.8 النصي للقرارات (فهرس بالسيناريو لا بالقرار — خلل اكتشف وأصلح) + سجل الرفض بأساس كل رفض + تنفيذ SIMULATION_ONCE من حصيلة بوابة 9 + مسارا قراءة overview/alerts + صفحة Next الوحيدة / بخمسة تبويبات بشadcn وتذييل ثابت mt-auto واستجابة كاملة.
- الاختبارات (10-g): 26 وحدة جديدة (test_mirror: بذرة ATR والاستدعاء الذاتي وسياسة المخزن الدائري وآلة القطبية بالتأكيد المتأخر والإبطال القطبي والقوة tanh وقطبية المناطق والمعرفات الفريدة والدمج المتساوي ودلالة أسماء الأحداث وحمولة الثمانية حقول بلا أسرار وحتمية D-07 وفحص المصدر وحتمية السلسلة + test_composition: مطابقة أرقام البوابات و13 حقلاً وثلاثة أقسام أثر وحتمية بايت-بايت وقانونية jsonschema) + 9 تكاملية (هجرة 0009 صعودًا وهبوطًا وإعادة والقيد الفريد + الويبهوك الحي بالخطوات الثماني مع اشتراك NATS فعلي وسباق المعالجة السريعة موثق) + إصلاح خلل كامن في عرّافة خاصية الجلسات (حد end=1440: المشية الدائرية كانت تخالف الدلالة الخطية — بناء الفترة الصريح بثلاث حالات موثق في الاختبار نفسه).
- البوابة (10-h): verify_phase10 بإحدى وعشرين فحصًا: قائمة §51 بندًا بندًا (17/17 بأوامر تحقيقها) + صفر خرق بنيوي لمصدر Pine + المرآة الحية تطابق الحصيلة بايت-بايت وكل الصفوف ضمن التسامح + خطوات الويبهوك 1-7 حية (401/422/إقرار بمفتاح الخادم/مكرر DUPLICATE) + الهجرة 0009 حية + اللوحة 13 حقلاً بأرقام البوابات + الأثر بثلاثة أقسام + 45 رفضًا + SIMULATION_ONLY بمقاييس بوابة 9 + تفتيش سيناريو كامل السلسلة (اشتعال ⇒ قرار مرخّص ⇒ نية أمر ⇒ صفقة موسومة INVALIDATION_FIRST) + حتمية وقانونية + الحافة والصفحة حية.
- E2E بالوكيل الآلي (متطلب البوابة): عبر مدخل البوابة (localhost:81): الصفحة تختبر ببيانات فعلية (25 سيناريو و45 رفضًا في التبويبات) والأثر القابل للطي يفتح بتفسير §2.8 الكامل والتنفيذ يعرض أرقام بوابة 9 الحرفية وتنبيهات الويبهوك تظهر بسجلها (CHOCH/PROCESSED...) وويبهوك عبر سلسلة D-09 الكاملة (Next→بوابة→FastAPI) يقر والمكرر عبر المسارين بنفس المفتاح — وصفر أخطاء وتحذيرات وحدة تحكم (React DevTools الإخباري فقط) وتذييل mt-auto مثبت بنيويًا ولا تمرير أفقي على 390px.
- البوابات النهائية: make gate كامل المراحل (lint كل الفحوص + mypy strict 232 ملفًا + imports 6 عقود + test 2387) وintegration 54 (مستقر عبر تشغيلين) وschemas check 72 وverify-phase10 = 21 أخضر.
- الإغلاق: ADR-028 (كائن البوابات واحد والمرآة المستقلة ومفتاح الخادم والتوكن بالاستعلام) + قسم المرحلة 10 في progress.md وسطر الجلسة + الحصيلة docs/mirror/phase10.

Stage Summary:
- **بوابة المرحلة 10 مغلقة رسميًا — MVP-DoD §51 مكتمل التعريف**: «قائمة §51 محققة بندًا بندًا بأوامر تحقق + تفتيش صفقة/سيناريو كامل السلسلة + make gate أخضر شاملًا + اللوحة تعرض بيانات فعلية» — الأركان الأربعة محققة وموثقة.
- **أهم درس هندسي في المرحلة**: المرآة المستقلة (منافذ كتبت من مصدر Pine لا من المحرك) هي التي جعلت الاتفاق شهادة حقيقية — أربعة أخطاء ترجمة كان كلهان سيمرران بصمت بنسخ الكود، منها تصادم المعرفات الذي أفسد 191 حدث اجتياح وسياسة ATR التي تقلب القرارات الحدية.
- **الحصيلة**: pine/ كاملة (مكتبة + مؤشر + توثيق) + مرآة D-08 بحصيلة قابلة لإعادة الإنتاج + هجرة 0009 + apps/api موسع بالكامل + حافة Next + لوحة / بخمسة تبويبات + 12 مخططًا (72) + 2387 اختبارًا + 21 فحص بوابة.
- **التالي بحسب الخطة (بعد MVP)**: المرحلة 11 محول التنفيذ (testnet وآلة حالة الأوامر وتعبئات وتسوية وحقن فشول §24.6) ثم 12 مختبر التعلم ثم 13 المباشر المتحكَّم — كلٌّ ببوابته من §46.
