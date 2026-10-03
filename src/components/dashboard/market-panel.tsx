"use client";

/** لوحة معلومات السوق — §35.2 حرفيًا (ثلاثة عشر حقلاً). */

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { PanelField } from "@/lib/dashboard-types";

const FIELD_LABELS: Record<string, string> = {
  market_regime: "Market Regime",
  htf_bias: "HTF Bias",
  mtf_setup_state: "MTF Setup State",
  liquidity_above_below: "Liquidity Above / Below",
  flow_state: "Flow State",
  delta: "Delta",
  volatility_state: "Volatility State",
  session: "Session",
  macro_risk: "Macro Risk",
  active_scenario: "Active Scenario",
  trigger_status: "Trigger Status",
  risk_status: "Risk Status",
  execution_status: "Execution Status",
};

function toneFor(key: string, value: string): "default" | "destructive" | "secondary" | "outline" {
  if (key === "risk_status" && value.startsWith("مرفوض")) return "destructive";
  if (key === "risk_status" && value === "مرخّص") return "default";
  if (key === "execution_status") return "outline";
  return "secondary";
}

export function MarketPanel({ panel }: { panel: PanelField[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">لوحة المعلومات الدنيا — §35.2</CardTitle>
        <p className="text-xs text-muted-foreground">
          ثلاثة عشر حقلًا حرفيًا من الخطة — لقطة آخر شريط من التوليف القانوني
        </p>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {panel.map((field) => (
            <div
              key={field.key}
              className="flex flex-col gap-1 rounded-lg border border-border/60 bg-card p-3 transition-colors hover:bg-accent/40"
            >
              <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                {FIELD_LABELS[field.key] ?? field.key}
              </span>
              <Badge
                variant={toneFor(field.key, field.value)}
                className="w-fit max-w-full truncate font-mono text-xs"
                title={field.value}
              >
                {field.value}
              </Badge>
              {field.detail ? (
                <span className="text-[11px] leading-4 text-muted-foreground" dir="auto">
                  {field.detail}
                </span>
              ) : null}
            </div>
          ))}
        </div>
        <Separator className="my-4" />
        <p className="text-[11px] text-muted-foreground" dir="auto">
          «أثمن من ملصق نسبة شرائية» — اللوحة سياق قرار لا إشارة تداول
        </p>
      </CardContent>
    </Card>
  );
}
