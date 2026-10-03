"use client";

/** التنفيذ والتنبيهات — وضع MVP المعلن (§28/§51) وسجل تسليم الويبهوك (§31.6). */

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import type { AlertRecord, ExecutionView, WebhookEventView } from "@/lib/dashboard-types";

const STATUS_TONE: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  RECEIVED: "secondary",
  PROCESSED: "default",
  DUPLICATE: "outline",
  REJECTED_AUTH: "destructive",
  REJECTED_SCHEMA: "destructive",
  REJECTED_CANONICAL: "destructive",
};

export function ExecutionTab({
  execution,
  alerts,
  alertLog,
}: {
  execution: ExecutionView;
  alerts: WebhookEventView[];
  alertLog: AlertRecord[];
}) {
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">التنفيذ — §28 + §51</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="font-mono">
              {execution.mode}
            </Badge>
            <span className="text-xs text-muted-foreground" dir="auto">
              القبول القانوني في محرك الإعادة الخارجي — التنفيذ الحي مؤجل للمرحلة 11
            </span>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Metric label="صفقات موسومة" value={String(execution.trades_count)} />
            <Metric
              label="التوقع الصافي (R)"
              value={execution.net_expectancy_r.toFixed(3)}
              tone={execution.net_expectancy_r >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}
            />
            <Metric
              label="عامل الربح"
              value={execution.profit_factor === null ? "—" : execution.profit_factor.toFixed(3)}
            />
            <Metric label="معدل الفوز" value={`${(execution.win_rate * 100).toFixed(1)}%`} />
          </div>
          <Separator className="my-3" />
          <p className="font-mono text-[10px] text-muted-foreground" dir="auto">
            {execution.report_ref}
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground" dir="auto">
            القياس الصادق لا التجميل: هذه أرقام الإعادة الآلية الموثقة (بوابة 9) على
            العينة المرجعية — المعايرة مختبر التعلم بعد MVP.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">تنبيهات الويبهوك — §31.6</CardTitle>
          <p className="text-xs text-muted-foreground">
            سجل التسليم: الإقرار فوري والمعالجة خلفية (§36) — الأحدث أولًا
          </p>
        </CardHeader>
        <CardContent>
          <ScrollArea className="max-h-[380px] pr-3">
            {alertLog.length === 0 && alerts.length === 0 ? (
              <p className="text-xs text-muted-foreground" dir="auto">
                لا تنبيهات مستلمة بعد — أرسل تنبيهًا تجريبيًا إلى ‎/api/tv/webhook?token=…
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {alertLog.map((a) => (
                  <div
                    key={a.alert_key + a.received_at}
                    className="flex flex-col gap-1 rounded-lg border border-border/60 p-3 sm:flex-row sm:items-center sm:gap-3"
                  >
                    <Badge variant={STATUS_TONE[a.status] ?? "secondary"} className="w-fit font-mono text-[11px]">
                      {a.status}
                    </Badge>
                    <div className="min-w-0 flex-1">
                      <p className="font-mono text-xs">
                        {a.event} · {a.instrument} · {a.price}
                      </p>
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {new Date(a.received_at).toLocaleString("en-GB", { hour12: false })}
                        {a.processed_at
                          ? ` → ${new Date(a.processed_at).toLocaleTimeString("en-GB", { hour12: false })}`
                          : " → (قيد المعالجة)"}
                      </span>
                      {a.processing_result?.detail ? (
                        <p className="mt-0.5 text-[11px] text-muted-foreground" dir="auto">
                          {a.processing_result.detail}
                        </p>
                      ) : null}
                    </div>
                  </div>
                ))}
                {alerts
                  .filter((v) => !alertLog.some((a) => a.alert_key.startsWith(v.alert_key.slice(0, 12))))
                  .map((v) => (
                    <div key={v.alert_key + v.received_at} className="flex items-center gap-3 rounded-lg border border-border/40 p-3 opacity-70">
                      <Badge variant={STATUS_TONE[v.status] ?? "secondary"} className="font-mono text-[11px]">
                        {v.status}
                      </Badge>
                      <span className="font-mono text-xs">
                        {v.event} · {v.instrument}
                      </span>
                    </div>
                  ))}
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border/60 p-3">
      <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span className={`font-mono text-lg ${tone ?? ""}`}>{value}</span>
    </div>
  );
}
