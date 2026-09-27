#!/usr/bin/env bash
# upload-watcher.sh — طبقة موثوقية استلام الملفات
# الغرض: مراقبة upload/ على مدار الساعة، والتقاط أي ملف يصل إليه فور اكتمال كتابته،
# ونسخه فورًا إلى received/ (صندوق الاستقبال الدائم) حتى لا يضيع إذا نُظّف upload/
# أو أعادت المنصة إنشاءه.
# التشغيل: nohup bash /home/z/my-project/.zscripts/upload-watcher.sh >/dev/null 2>&1 &
# الفحص:  pgrep -f upload-watcher.sh

set -u

UPLOAD_DIR="/home/z/my-project/upload"
RECEIVED_DIR="/home/z/my-project/received"
LOG_FILE="$RECEIVED_DIR/.arrival-log"
STATE_FILE="$RECEIVED_DIR/.watcher-state"

mkdir -p "$RECEIVED_DIR"
chmod 777 "$RECEIVED_DIR" 2>/dev/null || true
touch "$LOG_FILE" "$STATE_FILE"

declare -A COPIED
# استرجاع حالة سابقة حتى لا تُعاد النسخ بعد إعادة تشغيل المراقب
while IFS='|' read -r p s; do
  [ -n "$p" ] && COPIED["$p"]="$s"
done < "$STATE_FILE"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }

log "=== watcher started (pid $$) ==="

while true; do
  while IFS= read -r -d '' f; do
    [ -f "$f" ] || continue
    sz=$(stat -c '%s' "$f" 2>/dev/null) || continue
    # سبقت نسخته بنفس الحجم (أو نفس النسخة)؟ تجاوز
    [ "${COPIED[$f]:-}" = "$sz" ] && continue
    # انتظار ثبات الحجم على فاصل ثانية (التأكد من اكتمال الكتابة وليس ملفًا منتصف النقل)
    sz2=$(sleep 1; stat -c '%s' "$f" 2>/dev/null) || continue
    [ "$sz" = "$sz2" ] || continue
    # اسم آمن ضد تصادم الملفات المتكررة (نسخة جديدة تحمل طابعًا زمنيًا)
    base=$(basename "$f")
    dest="$RECEIVED_DIR/$base"
    if [ -e "$dest" ]; then
      dest="$RECEIVED_DIR/$(date +%Y%m%d-%H%M%S)__$base"
    fi
    if cp -- "$f" "$dest" 2>>"$LOG_FILE"; then
      COPIED["$f"]="$sz"
      printf '%s|%s\n' "$f" "$sz" >> "$STATE_FILE"
      chmod 666 "$dest" 2>/dev/null || true
      log "SNAPSHOT: '$f' ($sz bytes) -> '$dest'"
    else
      log "ERROR: failed to copy '$f'"
    fi
  done < <(find "$UPLOAD_DIR" -maxdepth 3 -type f -print0 2>/dev/null)
  sleep 1
done
