/**
 * ─────────────────────────────────────────────────────────────────────────────
 * Upload Reliability Watcher — طبقة موثوقية استلام الملفات (نمط Next الرسمي)
 * ─────────────────────────────────────────────────────────────────────────────
 * ملف الدخيل لـ instrumentation يجب أن يبقى رفيعًا: يستورد التنفيذ ديناميكيًا
 * داخل حرس بيئة nodejs فقط، لأن الاستيرادات الساكنة لوحدات node:* تُفسد بناء
 * بيئة edge وتمنع تنفيذ register كليًا (خطأ Ecmascript file had an error).
 *
 * التنفيذ الفعلي في src/lib/upload-watcher.ts.
 * ─────────────────────────────────────────────────────────────────────────────
 */

export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./lib/upload-watcher");
  }
}
