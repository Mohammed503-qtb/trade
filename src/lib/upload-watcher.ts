/**
 * ─────────────────────────────────────────────────────────────────────────────
 * Upload Reliability Watcher — التنفيذ الفعلي
 * ─────────────────────────────────────────────────────────────────────────────
 * يُستورد ديناميكيًا من src/instrumentation.ts داخل حرس بيئة nodejs فقط،
 * ولذلك تُستورد وحدات node:* هنا بأمان دون إفساد بناء بيئة edge.
 *
 * المشكلة التي يحلها:
 *   بوابة الترحيل قد تُسقط ملفات upload/ أو تُفرغ المجلد (مُدار من المنصة بملكية
 *   root). أي ملف يصل قد يختفي قبل قراءته.
 *
 * الحل:
 *   مراقب داخل عملية الخادم نفسها يفحص upload/ كل ثانية، وعند استقرار حجم أي
 *   ملف عبر استطلاعين متتاليين ينسخه فورًا إلى received/ (صندوق الاستقبال
 *   الدائم). عمر المراقب = عمر الخادم، ويعود تلقائيًا مع كل إقلاع للحاوية.
 *
 * ضمانات:
 *   - لا يرمي استثناءً خارج نفسه أبدًا؛ تعطيله لا يعطل التطبيق.
 *   - حالة واحدة فقط (globalThis + pidfile) مهما أعاد HMR التحميل.
 *   - أسماء آمنة ضد التصادم؛ سجل وصول كامل في received/.arrival-log.
 *   - خامد بأمان في بيئة النشر إذا لم يوجد مجلد upload/.
 * ─────────────────────────────────────────────────────────────────────────────
 */

import * as fsSync from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";

// حارس حالة-واحدة داخل نفس العملية: HMR قد يعيد استدعاء register
const g = globalThis as unknown as { __uploadWatcherActive?: boolean };

function ts(): string {
  return new Date().toISOString().replace("T", " ").replace("Z", "");
}

async function appendLog(logFile: string, line: string): Promise<void> {
  try {
    await fsp.appendFile(logFile, `[${ts()}] ${line}\n`);
  } catch {
    /* السجل لا يعطل المراقب أبدًا */
  }
}

export async function startUploadWatcher(): Promise<void> {
  if (g.__uploadWatcherActive) return;

  try {
    const projectRoot = process.cwd();
    // مصادر المراقبة: upload (تثبيت سحابي للبوابة) + inbox (صندوق المستخدم المرئي)
    const sourceDirs = [
      path.join(projectRoot, "upload"),
      path.join(projectRoot, "inbox"),
    ];
    const receivedDir = path.join(projectRoot, "received");
    const logFile = path.join(receivedDir, ".arrival-log");
    const stateFile = path.join(receivedDir, ".watcher-state");
    const pidFile = path.join(receivedDir, ".node-watcher.pid");

    await fsp.mkdir(receivedDir, { recursive: true });
    await fsp.chmod(receivedDir, 0o777).catch(() => {});

    // تحديد المصادر الفعلية: inbox ننشئه دائمًا (ملكنا)، وupload ننشئه في التطوير
    // فقط؛ في بيئة النشر بلا مصادر → خامد بأمان.
    const wanted: string[] = [];
    for (const dir of sourceDirs) {
      if (fsSync.existsSync(dir)) {
        wanted.push(dir);
        continue;
      }
      const isInbox = dir.endsWith(`${path.sep}inbox`);
      if (isInbox || process.env.NODE_ENV === "development") {
        await fsp.mkdir(dir, { recursive: true });
        await fsp.chmod(dir, 0o777).catch(() => {});
        wanted.push(dir);
      }
    }
    if (wanted.length === 0) return;

    // ── حارس الحالة-الواحدة بين العمليات (pidfile) ──
    try {
      const prev = parseInt((await fsp.readFile(pidFile, "utf8")).trim(), 10);
      if (Number.isInteger(prev) && prev !== process.pid) {
        process.kill(prev, 0); // يرمي خطأ إذا كان الحامل السابق ميتًا
        await appendLog(
          logFile,
          `[node-watcher] skipped start: pid ${prev} already watching`,
        );
        return; // مراقب آخر حي — لا ازدواج
      }
    } catch {
      /* لا حامل حي للقفل → نستحوذ عليه */
    }
    await fsp.writeFile(pidFile, `${process.pid}\n`);

    const cleanup = () => {
      try {
        if (
          fsSync.readFileSync(pidFile, "utf8").trim() === String(process.pid)
        ) {
          fsSync.rmSync(pidFile, { force: true });
        }
      } catch {
        /* ignore */
      }
    };
    process.on("exit", cleanup);
    // تنظيف فقط دون اختطاف إشارات المنصة (بدون process.exit)
    process.on("SIGTERM", cleanup);
    process.on("SIGINT", cleanup);

    g.__uploadWatcherActive = true;
    await appendLog(
      logFile,
      `[node-watcher] started (pid ${process.pid}) watching: ${wanted
        .map((d) => path.basename(d))
        .join(", ")}`,
    );

    // ── استرجاع حالة مسبقة (متوافقة مع نسخة bash الاحتياطية) ──
    const copiedAtSize = new Map<string, number>();
    try {
      for (const line of (await fsp.readFile(stateFile, "utf8")).split("\n")) {
        const [p, s] = line.split("|");
        if (p && s && !Number.isNaN(Number(s))) copiedAtSize.set(p, Number(s));
      }
    } catch {
      /* لا حالة سابقة */
    }

    const lastSize = new Map<string, number>();
    const MAX_DEPTH = 3;

    const walk = async (dir: string, depth: number, out: string[]) => {
      if (depth > MAX_DEPTH) return;
      const entries = await fsp.readdir(dir, { withFileTypes: true });
      for (const e of entries) {
        const full = path.join(dir, e.name);
        if (e.isSymbolicLink()) continue; // لا حلقات رمزية
        if (e.isDirectory()) await walk(full, depth + 1, out);
        else if (e.isFile()) out.push(full);
      }
    };

    const tick = async () => {
      try {
        const files: string[] = [];
        for (const dir of wanted) {
          await walk(dir, 1, files);
        }

        // تقليم حالات الملفات التي اختفت (تسريب ذاكرة = لا)
        const seen = new Set(files);
        for (const prev of lastSize.keys()) {
          if (!seen.has(prev)) lastSize.delete(prev);
        }

        for (const file of files) {
          const size = (await fsp.stat(file)).size;
          if (copiedAtSize.get(file) === size) continue; // مؤمَّنة بنفس الحجم
          if (lastSize.get(file) !== size) {
            // لم تستقر عبر استطلاعين متتاليين بعد — ربما منتصف نقل
            lastSize.set(file, size);
            continue;
          }

          // مستقرة → التقاط فوري قبل أي تنظيف محتمل للمجلد
          const base = path.basename(file);
          let dest = path.join(receivedDir, base);
          if (fsSync.existsSync(dest)) {
            const stamp = new Date()
              .toISOString()
              .replace(/[-:T]/g, "")
              .slice(0, 14);
            dest = path.join(receivedDir, `${stamp}__${base}`);
          }
          await fsp.copyFile(file, dest);
          await fsp.chmod(dest, 0o666).catch(() => {});
          copiedAtSize.set(file, size);
          await fsp.appendFile(stateFile, `${file}|${size}\n`);
          await appendLog(
            logFile,
            `[node-watcher pid ${process.pid}] SNAPSHOT: '${file}' (${size} bytes) -> '${dest}'`,
          );
        }
      } catch {
        /* الاستطلاع لا يرمي أبدًا */
      }
    };

    const timer = setInterval(() => {
      void tick();
    }, 1000);
    // المؤقّت لا يمنع الخادم من الإغلاق أبدًا
    if (typeof timer.unref === "function") timer.unref();
  } catch (err) {
    // فشل تشغيل المراقب لا يعطل التطبيق أبدًا
    console.warn("[upload-watcher] failed to start:", err);
  }
}

// يشغَّل فور الاستيراد الديناميكي من instrumentation
await startUploadWatcher();
