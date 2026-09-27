#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════════
# entrypoint.sh — نقطة دخول موحّدة لصورة engine (المواصفة D-01)
# ───────────────────────────────────────────────────────────────────────────────
# SERVICE (من ARG وقت البناء — compose يمرره لكل خدمة — أو environment وقت
# التشغيل) يحدد العملية:
#   api      → uvicorn engine_api.main:app   (يستمع على 0.0.0.0 داخل الحاوية؛
#              النشر الخارجي يظل loopback عبر ports في docker-compose)
#   worker   → python -m engine_worker       (خط الأنابيب الحي)
#   replay   → python -m engine_replay args… (CLI عند الطلب — profile مستقل)
#   migrate  → alembic upgrade head          (one-shot؛ alembic.ini على /app)
#   غير ذلك  → exec "$@"                     (تمرير مباشر لأمر عارض)
# قاعدة §37.1: لا أسرار هنا — كل الإعدادات من بيئة التشغيل حصرًا.
# ═══════════════════════════════════════════════════════════════════════════════
set -eu

: "${SERVICE:=worker}"

case "${SERVICE}" in
  api)
    exec uvicorn engine_api.main:app \
      --host "${ENGINE_API_HOST:-0.0.0.0}" \
      --port "${ENGINE_API_PORT:-4001}"
    ;;
  worker)
    exec python -m engine_worker
    ;;
  replay)
    exec python -m engine_replay "$@"
    ;;
  migrate)
    # alembic.ini على جذر /app (جذر engine/) — تقرأه المهمة 0.6؛
    # الاتصال من ENGINE_DATABASE_URL في بيئة التشغيل (تشير إلى خدمة postgres)
    exec alembic upgrade head
    ;;
  *)
    exec "$@"
    ;;
esac
