# infra/ — مواصفة النشر للخادم الهدف (قرار D-01)

> **حالة هذه الوثيقة والملفات:** الـsandbox الحالي **لا يملك Docker** — كل ما هنا
> **مواصفة قانونية** تُختبر بنيويًا الآن وتُبنى فعليًا **على الخادم الهدف لاحقًا**
> (التشغيل المزدوج: الـsandbox يستخدم `infra/local/supervisor.py`، والهدف يستخدم
> Compose — نفس الطوبولوجيا المنطقية، طريقتا إقلاع مختلفتان فقط).

## المحتويات

| المسار | الدور |
|---|---|
| `docker-compose.yml` | الخدمات الثماني + الشبكة + volumes (المواصفة القانونية) |
| `dockerfiles/Dockerfile.engine` | صورة موحّدة لكل خدمات المحرك (multi-stage عبر uv) |
| `dockerfiles/entrypoint.sh` | مدخل مرن: `SERVICE` يحدد api / worker / replay / migrate |
| `dockerfiles/healthcheck.py` | فحص صحة engine-api داخل الحاوية (stdlib فقط) |
| `local/` | وضع الـsandbox (supervisor + ثنائيات user-space) — لا علاقة له بالهدف |

## الفرق عن وضع الـsandbox

| البند | sandbox (supervisor) | الخادم الهدف (هذه المواصفة) |
|---|---|---|
| الإقلاع | `make infra-up` (supervisor.py) | `docker compose … up -d` |
| PostgreSQL | ثنائيات مضمّنة user-space على 5543 | حاوية `postgres:16-alpine` (منفذ داخلي 5543) |
| NATS / MinIO | ثنائيات رسمية user-space | حاويات `nats:2.10-alpine` / `minio/minio` |
| عناوين الخدمات | `127.0.0.1:<port>` | أسماء الخدمات على شبكة `engine-internal` |
| الهجرة | `make migrate` (alembic مباشرة) | خدمة `migrate` one-shot ضمن depends_on |
| ما يُكشف خارجيًا | لا شيء (منفذ المنصة الوحيد لـNext) | **engine-api فقط على `127.0.0.1:4001`** |

## التشغيل على الخادم الهدف

المتطلب: Docker Engine + **Docker Compose v2.24+** (صيغة `env_file.required:false`)
وأكتمال المهمة 0.6 (ملف `alembic.ini` على جذر `engine/` — بناء الصورة قبله
يفشل بوضوح وهذا مقصود: fail-fast).

```bash
cd engine                                # جذر الـworkspace البايثوني

# 1) البيئة (مرة واحدة) — انسخ النموذج وعدّل الأسرار
cp .env.example .env

# 2) الإقلاع الكامل (يبني الصورة + ينتظر صحة كل شيء + يشغل migrate وstorage-init)
docker compose -f infra/docker-compose.yml --env-file .env up -d

# 3) المتابعة
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs -f engine-worker engine-api

# 4) هجرة يدوية عند اللزوم (خدمة migrate أصلًا تعمل ضمن up)
docker compose -f infra/docker-compose.yml --env-file .env run --rm migrate

# 5) الإعادة عند الطلب (profile مستقل — لا يقلع مع up الافتراضي)
docker compose -f infra/docker-compose.yml --env-file .env --profile replay run --rm engine-replay --help

# 6) الإيقاف / الإيقاف مع مسح البيانات
docker compose -f infra/docker-compose.yml --env-file .env down
docker compose -f infra/docker-compose.yml --env-file .env down -v   # يمحو volumes (خطر!)
```

> **لماذا `--env-file .env` صراحةً؟** صيغة `${VAR:-default}` في المواصفة تُستوفى
> من ملف البيئة الذي يمرَّر للـcompose، وليس من `env_file` الخاص بالحاويات.
> دون هذه الراية يعمل Compose على `infra/.env` (مجلد الملف) ولن يرى قيمك —
> والمواصفة لن تنكسر، لكنها ستعمل بالقيم الافتراضية (وضع تطوير).

## متغيرات البيئة المطلوبة (استنادًا إلى `engine/.env.example`)

| المتغير | الاستخدام في compose | ملاحظات |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | خدمة postgres + بناء `ENGINE_DATABASE_URL` | افتراضي: `engine` / `engine` / `engine` |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | بيانات دخول MinIO (`MINIO_ROOT_*`) وstorage-init | **غيّرهما على الهدف** |
| `S3_BUCKET` | اسم حزمة الخام | افتراضي: `engine-raw` |
| `S3_SECURE` | عميل التخزين | افتراضي: `false` (شبكة داخلية) |
| `TV_WEBHOOK_SECRET` | engine-api (المرحلة 10) | افتراضي فارغ — **عيّنه قبل أي استخدام حي** |
| `BINANCE_API_BASE` / `BINANCE_VISION_BASE` / `ENGINE_SYMBOL` | engine-worker (D-02) | لها افتراضيات عامة |
| `ENGINE_TIMEFRAME_HTF/MTF/LTF` | engine-worker (D-05) | افتراضي: `1h / 15m / 1m` |

**لاحظ:** `ENGINE_DATABASE_URL` و`NATS_URL` و`S3_ENDPOINT` تُعرَّف في `.env`
بصيغة sandbox (عناوين `127.0.0.1`) — **المواصفة تعيد تعيينها صراحةً** في
`environment` بأسماء الخدمات (`postgres` / `nats` / `minio`)، والتعيين الصريح
يتقدم على `env_file`، فلا تتسرب عناوين الـsandbox إلى الحاويات أبدًا.
غياب `engine/.env` كله لا يكسر النشر: `required:false` + افتراضيات `${VAR:-default}`.

## وصول لوحة Next إلى engine-api على نفس الخادم

المبدأ الأمني (A.3): لا شيء يُكشف خارج docker إلا engine-api على loopback:

- **لوحة Next على نفس الخادم الهدف:** من الشيفرة الخلفية للوحة، ناده loopback
  مباشرة: `http://127.0.0.1:4001/...` (لا حاجة لأي فتح خارجي).
- **لوحة Next على خادم منفصل/منصة البوابة:** أضف بروكسي عكسي (مثل Caddy/Nginx)
  على الخادم الهدف يحوّل مسارًا واحدًا إلى `127.0.0.1:4001` مع TLS — أو استخدم
  نمط بوابة المنصة `?XTransformPort=4001` إن كانت اللوحة مستضافة على منصة
  الـsandbox نفسها وتملك وصول شبكة إلى الخادم الهدف.
- **ممنوع:** تغيير النشر إلى `4001:4001` (بدون `127.0.0.1`) — هذا يكشف المحرك
  للعالم الخارجي ويخرق القرار D-09.

## التحقق البنيوي (داخل الـsandbox — لا Docker)

```bash
cd engine
unset VIRTUAL_ENV && uv run --no-sync python scripts/validate-compose.py
```

16 فحصًا آليًا: اكتمال الخدمات الثماني، فحوص الصحة، النشر loopback فقط،
شروط depends_on، JetStream، volumes المسماة، profile الـreplay، env_file
الاختياري، إشارة قاعدة البيانات لاسم الخدمة، إعدادات postgres المحافظة،
ودلالات one-shot. أي فشل = رسالة عربية + خروج 1.

## قرارات موثقة وقيود معروفة

1. **`alembic.ini` يصل مع المهمة 0.6** — سطر `COPY alembic.ini` في Dockerfile
   مقصود: البناء قبله يفشل بوضوح بدل فشل صامت لخدمة migrate لاحقًا.
2. **alembic في مجموعة dev فقط** في القفل — الصورة تثبته بالإصدار المقفول
   نفسه (`1.20.0` من `uv.lock`) لخدمة migrate؛ متى نُقل لتبعيات تشغيل حُذف
   سطر تثبيته من Dockerfile.
3. **طبقة الاعتمادات:** `uv sync --no-install-workspace` في مرحلة deps ثم
   تركيب حزم الـworkspace بعد نسخ الشيفرة — مثبت تجريبيًا أن تركيبها بلا
   مصدر "ينجح" صامتًا بلا مسارات استيراد (`.pth` فارغة).
4. **يوصى عند النشر الفعلي:** إنشاء `engine/.dockerignore` (استبعاد
   `.venv/` و`data/` و`.env` ومخلفات الأدوات) لضم سياق البناء، وتثبيت
   digests للصور (`postgres@sha256:…`) بدل الوسوم — كلاهما خارج نطاق هذه
   المهمة (قيود المسارات) ومسجل هنا للمسؤول عن النشر.
5. **سجلات دوّارة:** كل الخدمات تستخدم `json-file` بحد 10MB×3 — نظافة
   تشغيلية على الهدف.
