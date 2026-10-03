"use client";

/** أثر الاستدلال القابل للطي — §35.3 حرفيًا (لماذا نشط/ماذا ضده/لماذا الانتظار). */

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown } from "lucide-react";
import type { ReasoningTrace } from "@/lib/dashboard-types";

export function ReasoningTab({ traces }: { traces: ReasoningTrace[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">أثر الاستدلال — §35.3</CardTitle>
        <p className="text-xs text-muted-foreground">
          «أثمن من ملصق BUY 91%» — الأدلة الصريحة مؤيدة ومعارضة لا نسبة مصقولة
        </p>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-3">
          {traces.map((t) => (
            <Collapsible key={t.scenario_id} className="rounded-lg border border-border/60">
              <CollapsibleTrigger className="flex w-full flex-wrap items-center gap-2 p-3 text-start hover:bg-accent/40">
                <Badge variant="outline" className="font-mono text-[11px]">
                  {t.direction === "LONG" ? "▲" : "▼"} {t.template}
                </Badge>
                <span className="truncate font-mono text-[11px] text-muted-foreground">
                  {t.scenario_id.slice(0, 21)}…
                </span>
                <ChevronDown className="ms-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform [[data-state=open]>&]:rotate-180" />
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="grid grid-cols-1 gap-3 border-t border-border/60 p-3 md:grid-cols-3">
                  <TraceColumn
                    title="WHY ACTIVE? — لماذا نشط؟"
                    items={t.why_active}
                    tone="border-s-emerald-500"
                  />
                  <TraceColumn
                    title="WHAT AGAINST IT? — ماذا ضده؟"
                    items={t.what_against}
                    tone="border-s-red-500"
                  />
                  <TraceColumn
                    title="WHY WAIT? — لماذا الانتظار؟"
                    items={t.why_wait}
                    tone="border-s-amber-500"
                  />
                </div>
              </CollapsibleContent>
            </Collapsible>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function TraceColumn({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  return (
    <div className={`flex flex-col gap-2 border-s-2 ps-3 ${tone}`}>
      <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </span>
      {items.length === 0 ? (
        <span className="text-xs text-muted-foreground" dir="auto">
          — (لا بنود مرصودة)
        </span>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {items.map((item, i) => (
            <li key={i} className="text-xs leading-5" dir="auto">
              • {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
