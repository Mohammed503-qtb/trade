"use client";

/** السيناريوهات النشطة — الطبقتان 4-5 من §35.1 (السيناريو ومستوياته). */

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { ScenarioView } from "@/lib/dashboard-types";

const STATE_TONE: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  TRIGGERED: "default",
  PROPOSED: "secondary",
  PENDING_TRIGGER: "secondary",
  REJECTED_BY_RISK: "destructive",
  AUTHORIZED: "default",
  EXPIRED: "outline",
  INVALIDATED: "outline",
  COMPLETED: "outline",
};

export function ScenariosTab({ scenarios }: { scenarios: ScenarioView[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">السيناريوهات — الأحدث أولًا</CardTitle>
        <p className="text-xs text-muted-foreground">
          كل سيناريو استُنسخ من حدث سيولة مؤكد (D-04) — لا مقترح بلا مشغل
        </p>
      </CardHeader>
      <CardContent>
        <ScrollArea className="max-h-[520px] pr-3">
          <div className="flex flex-col gap-3">
            {scenarios.map((s) => (
              <div
                key={s.scenario_id}
                className="grid grid-cols-1 gap-3 rounded-lg border border-border/60 p-3 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]"
              >
                <div className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={STATE_TONE[s.state] ?? "secondary"} className="font-mono text-[11px]">
                      {s.state}
                    </Badge>
                    <Badge variant="outline" className="font-mono text-[11px]">
                      {s.direction === "LONG" ? "▲ LONG" : s.direction === "SHORT" ? "▼ SHORT" : s.direction}
                    </Badge>
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {s.template}
                    </span>
                  </div>
                  <span className="truncate font-mono text-[11px] text-muted-foreground" title={s.scenario_id}>
                    {s.scenario_id.slice(0, 21)}…
                  </span>
                  <div className="text-[11px] text-muted-foreground" dir="auto">
                    {new Date(s.created_time).toLocaleString("en-GB", { hour12: false })} — أدلة:{" "}
                    {s.evidence_count}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <LevelBox label="Entry" value={`${s.entry_price_low.toFixed(1)}–${s.entry_price_high.toFixed(1)}`} />
                  <LevelBox label="Stop" value={s.stop.toFixed(1)} tone="text-red-700 dark:text-red-400" />
                  <LevelBox label="Target" value={s.target_price.toFixed(1)} tone="text-emerald-700 dark:text-emerald-400" />
                  <div className="flex flex-col gap-1">
                    <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                      Score §2.6
                    </span>
                    <Progress value={Math.round(s.score * 100)} className="h-2" />
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {s.score.toFixed(3)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

function LevelBox({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span className={`font-mono text-sm ${tone ?? ""}`}>{value}</span>
    </div>
  );
}
