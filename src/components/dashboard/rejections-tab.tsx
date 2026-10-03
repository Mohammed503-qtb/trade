"use client";

/** سجل الرفض — لا-تداول §22 والكتم الموزون §22.2 بأساس كل رفض. */

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { RejectionView } from "@/lib/dashboard-types";

export function RejectionsTab({ rejections }: { rejections: RejectionView[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">سجل الرفض — §22 (لا-تداول)</CardTitle>
        <p className="text-xs text-muted-foreground">
          كل رفض موثق الأساس بتفسير §22.3 — «التدهور الآمن لا التداول الأعمى»
        </p>
      </CardHeader>
      <CardContent>
        <ScrollArea className="max-h-[520px] pr-3">
          <div className="flex flex-col gap-2">
            {rejections.map((r) => (
              <div
                key={r.decision_id}
                className="flex flex-col gap-1 rounded-lg border border-border/60 p-3 sm:flex-row sm:items-center sm:gap-3"
              >
                <Badge variant="destructive" className="w-fit font-mono text-[11px]">
                  {r.reason_code}
                </Badge>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs" dir="auto" title={r.explanation}>
                    {r.explanation}
                  </p>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {new Date(r.as_of).toLocaleString("en-GB", { hour12: false })} ·{" "}
                    {r.scenario_id?.slice(0, 18) ?? "—"}…
                  </span>
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
