/**
 * حافة الويبهوك العامة (D-09 + §36 + §6.4).
 *
 * TradingView يدفع POST/JSON إلى HTTPS عام على المنافذ 80/443 فقط —
 * والمنصة تكشف منفذًا واحدًا (Caddy → هذا التطبيق). هذا المسار هو
 * «الحافة العامة»: يمرر الطلب كما هو إلى FastAPI الداخلي عبر نمط
 * المنصة (‎?XTransformPort=4001‎) — بلا منفذ مكتوب في الشيفرة، والأصل
 * يُبنى من ترويسة الطلب المستلمة.
 *
 * لا معالجة هنا عمدًا (§36): المصادقة والتحقق والتكرار والحفظ والنشر
 * مسؤولية الخدمة الداخلية وحدها — الحافة تمرر وتقر بما يرجع.
 * الإقرار السريع (<3s) مطلب الطرفين معًا (§6.4).
 */

import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const INTERNAL_PORT = "4001";

export async function POST(request: Request): Promise<NextResponse> {
  // الأصل من ترويسة الطلب المستلمة (Caddy يمرر Host الأصلي) — نمط
  // المنصة حرفيًا: مسار نسبي + XTransformPort في الاستعلام فقط.
  const host =
    request.headers.get("x-forwarded-host") ??
    request.headers.get("host") ??
    "localhost:3000";
  const proto = request.headers.get("x-forwarded-proto") ?? "http";

  const incoming = new URL(request.url);
  const target = new URL(
    `/api/tv/webhook?XTransformPort=${INTERNAL_PORT}`,
    `${proto}://${host}`,
  );
  // التوكن (معامل الاستعلام) يمرر كما هو — لا أسرار تُفحص أو تخزن هنا.
  incoming.searchParams.forEach((value, key) => {
    if (key !== "XTransformPort") target.searchParams.set(key, value);
  });

  const body = await request.text();
  const upstream = await fetch(target, {
    method: "POST",
    headers: { "content-type": request.headers.get("content-type") ?? "application/json" },
    body,
    cache: "no-store",
    // إقرار سريع — لا انتظار معالجة خلفية أبدًا (§6.4).
    signal: AbortSignal.timeout(2_500),
  });

  const payload = await upstream.text();
  return new NextResponse(payload, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
