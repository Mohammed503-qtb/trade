#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# provision — تنزيل ثنائيات البنية التحتية إلى infra/local/bin
# (build_plan 0.4 — القرار D-01: تشغيل user-space بلا Docker)
#
# نسخ مثبتة حرفيًا (مبدأ إعادة الإنتاج §26.2 — لا "latest" عائم):
#   - nats-server 2.10.24        (GitHub releases — ثنائية Go رسمية)
#   - postgres 16.4              (Zonky embedded-postgres-binaries — maven central)
#   - seaweedfs (latest)          (استخراج من صورة Docker Hub chrislusf/seaweedfs)
#     ADR-006: MinIO OSS مؤرشف وحُذفت صوره — SeaweedFS البديل النشط
#     بنفس صورة Docker Hub المستخدمة في compose (توافق sandbox/هدف).
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BIN_DIR="$ENGINE_DIR/infra/local/bin"
TMP_DIR="$ENGINE_DIR/data/tmp/provision"
mkdir -p "$BIN_DIR" "$TMP_DIR"

NATS_VERSION="2.10.24"
ZONKY_VERSION="16.4.0"
SEAWEED_TAG="latest"

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; NC=$'\033[0m'
ok()   { echo "${GREEN}✓${NC} $1"; }
bad()  { echo "${RED}✗${NC} $1"; }
step() { echo "${YELLOW}── $1 ──${NC}"; }

download() { # url dest
    curl -fL --retry 3 --retry-delay 2 --connect-timeout 15 -o "$2" "$1"
}

# ───────────────────────── 1) nats-server ─────────────────────────
install_nats() {
    if [[ -x "$BIN_DIR/nats-server" ]] && "$BIN_DIR/nats-server" --version 2>/dev/null | grep -q "$NATS_VERSION"; then
        ok "nats-server $NATS_VERSION موجود أصلًا"; return 0
    fi
    step "تنزيل nats-server $NATS_VERSION"
    local url="https://github.com/nats-io/nats-server/releases/download/v${NATS_VERSION}/nats-server-v${NATS_VERSION}-linux-amd64.tar.gz"
    download "$url" "$TMP_DIR/nats.tar.gz"
    tar -xzf "$TMP_DIR/nats.tar.gz" -C "$TMP_DIR"
    install -m 0755 "$TMP_DIR/nats-server-v${NATS_VERSION}-linux-amd64/nats-server" "$BIN_DIR/nats-server"
    ok "nats-server $("$BIN_DIR/nats-server" --version 2>&1 | head -1)"
}

# ───────────────────────── 2) PostgreSQL (Zonky) ─────────────────────────
install_postgres() {
    if [[ -x "$BIN_DIR/pg_ctl" ]]; then
        ok "postgres (zonky) موجود أصلًا"; return 0
    fi
    step "تنزيل PostgreSQL $ZONKY_VERSION (Zonky embedded binaries)"
    local url="https://repo1.maven.org/maven2/io/zonky/test/postgres/embedded-postgres-binaries-linux-amd64/${ZONKY_VERSION}/embedded-postgres-binaries-linux-amd64-${ZONKY_VERSION}.jar"
    download "$url" "$TMP_DIR/pg.jar"
    # الجرة تحوي postgres-linux-x86_64.txz
    (cd "$TMP_DIR" && unzip -o -q pg.jar postgres-linux-x86_64.txz)
    mkdir -p "$TMP_DIR/pg-install"
    tar -xJf "$TMP_DIR/postgres-linux-x86_64.txz" -C "$TMP_DIR/pg-install"
    # تثبيت في bin/ مع بنية nxlib/ المجاورة (zonky يستخدم rpath نسبيًا)
    rm -rf "$BIN_DIR/pg"
    mv "$TMP_DIR/pg-install" "$BIN_DIR/pg"
    for b in postgres pg_ctl initdb psql pg_isready pg_controldata pg_basebackup createdb dropuser createuser; do
        local src="$BIN_DIR/pg/bin/$b"
        [[ -x "$src" ]] && ln -sf "$src" "$BIN_DIR/$b"
    done
    # الثنائيات في zonky تتوقع nxlib بجانب المسار المنفذ — الارتباطات الرمزية تكسر rpath؛
    # نستخدم الغلاف pg-start الذي يستدعي المسار الحقيقي دائمًا
    ok "postgres $("$BIN_DIR/pg/bin/postgres" --version 2>&1)"
}

# ───────────────────────── 3) SeaweedFS (من Docker Hub) ─────────────────────────
# قرار ADR-006: MinIO OSS مؤرشف نهائيًا وdl.min.io يرد 410 Gone، وصورة minio/minio
# محذوفة من Docker Hub كليًا. البديل المعتمد: SeaweedFS (S3-compatible نشط)
# بنفس صورة Docker Hub المستخدمة في compose للخادم الهدف — عميل minio-py
# يعمل ضده بلا أي تغيير كود (مُثبت باختبار تكامل كامل).
install_seaweedfs() {
    if [[ -x "$BIN_DIR/seaweedfs" ]]; then
        ok "seaweedfs موجود أصلًا"; return 0
    fi
    step "استخراج seaweedfs من صورة Docker Hub (chrislusf/seaweedfs:$SEAWEED_TAG)"
    local token index_manifest amd_digest manifest digest member
    token=$(curl -fsS "https://auth.docker.io/token?service=registry.docker.io&scope=repository:chrislusf/seaweedfs:pull" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
    index_manifest=$(curl -fsSL -H "Authorization: Bearer $token" \
        -H "Accept: application/vnd.oci.image.index.v1+json" \
        "https://registry-1.docker.io/v2/chrislusf/seaweedfs/manifests/$SEAWEED_TAG")
    amd_digest=$(echo "$index_manifest" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(next(m["digest"] for m in d["manifests"]
           if m["platform"]["architecture"] == "amd64" and m["platform"]["os"] == "linux"))
')
    manifest=$(curl -fsSL -H "Authorization: Bearer $token" \
        -H "Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json" \
        "https://registry-1.docker.io/v2/chrislusf/seaweedfs/manifests/$amd_digest")
    # الطبقة الكبيرة الأولى هي ثنائية weed (Go static ~80MB) — تنازليًا بالحجم
    for digest in $(echo "$manifest" | python3 -c '
import json, sys
m = json.load(sys.stdin)
for layer in sorted(m["layers"], key=lambda l: -l["size"]):
    print(layer["digest"])
'); do
        download "https://registry-1.docker.io/v2/chrislusf/seaweedfs/blobs/$digest" "$TMP_DIR/sw-layer.tar"
        member=$(tar -tf "$TMP_DIR/sw-layer.tar" 2>/dev/null | grep -E "usr/bin/weed$" | head -1 || true)
        if [[ -n "$member" ]]; then
            tar -xf "$TMP_DIR/sw-layer.tar" -C "$TMP_DIR" "$member"
            install -m 0755 "$TMP_DIR/$member" "$BIN_DIR/seaweedfs"
            break
        fi
        rm -f "$TMP_DIR/sw-layer.tar"
    done
    [[ -x "$BIN_DIR/seaweedfs" ]] || { bad "تعذر استخراج ثنائية weed"; return 1; }
    ok "seaweedfs: $("$BIN_DIR/seaweedfs" version 2>&1 | head -1 | cut -c1-60)"
}

# ───────────────────────── 4) .env من المثال ─────────────────────────
ensure_env() {
    if [[ ! -f "$ENGINE_DIR/.env" ]]; then
        cp "$ENGINE_DIR/.env.example" "$ENGINE_DIR/.env"
        ok "أُنشئ engine/.env من المثال (عدّل الأسرار قبل أي استخدام حقيقي)"
    else
        ok "engine/.env موجود"
    fi
}

# ───────────────────────── التنفيذ ─────────────────────────
echo "════════════ provision: ثنائيات البنية التحتية ════════════"
install_nats
install_postgres
install_seaweedfs
ensure_env
rm -rf "$TMP_DIR"
echo "════════════════════════════════════════════════════════════"
echo "${GREEN}اكتمل التجهيز في infra/local/bin/:${NC}"
ls -lh "$BIN_DIR" | grep -vE "^total|pg$" || true
echo "الخطوة التالية: make infra-up"
