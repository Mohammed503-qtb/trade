#!/usr/bin/env bash
# ═══════ doctor — فحص البيئة والتبعيات والإصدارات (build_plan 0.1) ═══════
set -uo pipefail

ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ENGINE_DIR"

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; NC=$'\033[0m'
PASS=0; FAIL=0

ok()   { echo "  ${GREEN}✓${NC} $1"; PASS=$((PASS+1)); }
bad()  { echo "  ${RED}✗${NC} $1"; FAIL=$((FAIL+1)); }
warn() { echo "  ${YELLOW}!${NC} $1"; }

echo "══════════════ doctor: AI Market Reasoning Engine ══════════════"

# 1. بايثون
echo "[1] Python"
PY_VER=$(uv run --no-sync python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null)
if [[ "$PY_VER" == "3.12."* ]]; then
  ok "Python $PY_VER (uv-managed)"
elif [[ -n "$PY_VER" ]]; then
  warn "Python $PY_VER — المستهدف 3.12، قد يعمل لكن غير مضمون"
else
  bad "لا يمكن تشغيل Python عبر uv — شغّل: uv sync"
fi

# 2. uv workspace متزامن
echo "[2] uv workspace"
if [[ -d .venv ]]; then
  VENV_COUNT=$(ls .venv/lib/python3.12/site-packages/ 2>/dev/null | grep -c '^engine_' || true)
  PKG_COUNT=18
  if (( VENV_COUNT >= PKG_COUNT )); then
    ok "workspace متزامن ($VENV_COUNT حزمة مثبتة)"
  else
    bad "workspace ناقص التزامن ($VENV_COUNT/$PKG_COUNT) — شغّل: make sync"
  fi
else
  bad "لا يوجد .venv — شغّل: make sync"
fi

# 3. الأدوات
echo "[3] أدوات الجودة"
for tool in ruff mypy lint-imports pytest alembic; do
  if uv run --no-sync "$tool" --version >/dev/null 2>&1 || uv run --no-sync python -c "import importlib.util as u; exit(0 if u.find_spec('$tool') else 1)" >/dev/null 2>&1; then
    VER=$(uv run --no-sync "$tool" --version 2>/dev/null | head -1)
    ok "${VER:-$tool}"
  else
    bad "$tool غير متاح"
  fi
done

# 4. ثنائيات البنية التحتية
echo "[4] ثنائيات infra (اختياري — infra-provision)"
BIN_DIR="infra/local/bin"
for bin_name in nats-server minio postgres; do
  if [[ -x "$BIN_DIR/$bin_name" ]]; then
    ok "$bin_name: $($BIN_DIR/$bin_name --version 2>/dev/null | head -1 | cut -c1-60 || echo 'موجود')"
  else
    warn "$bin_name غير منزّل بعد — شغّل: make infra-provision"
  fi
done

# 5. الإعدادات
echo "[5] الإعدادات"
if [[ -f .env ]]; then
  ok "engine/.env موجود"
  if grep -q "change-me" .env 2>/dev/null; then
    warn "قيم افتراضية (change-me) ما تزال في .env — مقبول في dev فقط"
  fi
else
  warn "engine/.env غير موجود — نسخة افتراضية من .env.example ستُستخدم"
fi

# 6. اتصال الخدمات (فقط إن كانت تُجيب — لا يفشل doctor عليها)
echo "[6] خدمات حية (استطلاع)"
[[ -f .env ]] && source <(grep -E '^[A-Z_]+=' .env | sed 's/^/export /') 2>/dev/null
PG_PORT="${POSTGRES_PORT:-5543}"; NATS_PORT=4222; MINIO_PORT="${S3_ENDPOINT#*:}"; MINIO_PORT="${MINIO_PORT:-9100}"; API_PORT="${ENGINE_API_PORT:-4001}"
declare -A PORTS=( [postgres]="$PG_PORT" [nats]=4222 [minio]="$MINIO_PORT" [engine-api]="$API_PORT" )
for svc in postgres nats minio engine-api; do
  port="${PORTS[$svc]}"
  if (echo > "/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    ok "$svc يستجيب على $port"
  else
    warn "$svc غير مشغل على $port (make infra-up يرفع البنية)"
  fi
done

echo "════════════════════════════════════════════════════════════════"
if (( FAIL > 0 )); then
  echo "${RED}doctor: $PASS نجح / $FAIL فشل${NC}"
  exit 1
fi
echo "${GREEN}doctor: كل الفحوصات الأساسية ناجحة ($PASS)${NC}"
