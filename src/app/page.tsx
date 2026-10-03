"use client";

/**
 * لوحة المحرك الدنيا — المرحلة 10 (§35.2 + §35.3 + §31.6).
 *
 * الصفحة الوحيدة الظاهرة: حالة السوق + السيناريوهات النشطة + أثر
 * الاستدلال + سجل الرفض + التنفيذ والتنبيهات — كل البيانات فعلية من
 * الواجهة الداخلية عبر نمط المنصة (‎?XTransformPort=4001‎).
 */

import { useCallback, useEffect, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { MarketPanel } from "@/components/dashboard/market-panel";
import { ScenariosTab } from "@/components/dashboard/scenarios-tab";
import { ReasoningTab } from "@/components/dashboard/reasoning-tab";
import { RejectionsTab } from "@/components/dashboard/rejections-tab";
import { ExecutionTab } from "@/components/dashboard/execution-tab";
import type { AlertRecord, DashboardOverview } from "@/lib/dashboard-types";

const API_BASE = "/api/dashboard";

export default function Home() {
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [alertLog, setAlertLog] = useState<AlertRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const [ovRes, alRes] = await Promise.all([
        fetch(`${API_BASE}/overview?XTransformPort=4001`, { cache: "no-store" }),
        fetch(`${API_BASE}/alerts?XTransformPort=4001&limit=50`, { cache: "no-store" }),
      ]);
      if (!ovRes.ok) throw new Error(`overview ${ovRes.status}`);
      const ov = (await ovRes.json()) as DashboardOverview;
      setOverview(ov);
      setError(null);
      if (alRes.ok) {
        const al = (await alRes.json()) as { alerts: AlertRecord[] };
        setAlertLog(al.alerts ?? []);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "خطأ غير معروف");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="sticky top-0 z-10 border-b border-border/60 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary font-mono text-sm font-bold text-primary-foreground">
              AM
            </span>
            <div className="leading-tight">
              <h1 className="text-sm font-semibold">AI Market Reasoning Engine</h1>
              <p className="text-[11px] text-muted-foreground">اللوحة الدنيا — المرحلة 10 (MVP)</p>
            </div>
          </div>
          <div className="ms-auto flex items-center gap-2">
            {overview ? (
              <Badge variant="outline" className="hidden font-mono text-[11px] sm:inline-flex">
                {overview.counts.risk_decisions} قرارًا · {overview.counts.authorized} ترخيصًا ·{" "}
                {overview.counts.rejected} رفضًا
              </Badge>
            ) : null}
            <Button
              variant="outline"
              size="sm"
              onClick={() => void load()}
              disabled={refreshing}
              aria-label="تحديث البيانات"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-5">
        {error ? (
          <Card className="border-destructive/40">
            <CardContent className="flex items-start gap-3 p-4">
              <AlertTriangle className="mt-0.5 h-5 w-5 text-destructive" />
              <div>
                <p className="text-sm font-medium">تعذر جلب بيانات اللوحة</p>
                <p className="font-mono text-xs text-muted-foreground">{error}</p>
                <p className="mt-1 text-xs text-muted-foreground" dir="auto">
                  تأكد من تشغيل الواجهة الداخلية (المنفذ 4001 عبر البوابة) ثم حدّث.
                </p>
              </div>
            </CardContent>
          </Card>
        ) : loading ? (
          <div className="flex flex-col gap-4">
            <Skeleton className="h-8 w-64" />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-24" />
              ))}
            </div>
            <Skeleton className="h-64" />
          </div>
        ) : overview ? (
          <Tabs defaultValue="market" className="w-full">
            <TabsList className="mb-4 flex h-auto flex-wrap">
              <TabsTrigger value="market">السوق — §35.2</TabsTrigger>
              <TabsTrigger value="scenarios">
                السيناريوهات ({overview.scenarios.length})
              </TabsTrigger>
              <TabsTrigger value="reasoning">أثر الاستدلال — §35.3</TabsTrigger>
              <TabsTrigger value="rejections">
                سجل الرفض ({overview.rejections.length})
              </TabsTrigger>
              <TabsTrigger value="execution">التنفيذ والتنبيهات</TabsTrigger>
            </TabsList>
            <TabsContent value="market">
              <MarketPanel panel={overview.panel} />
            </TabsContent>
            <TabsContent value="scenarios">
              <ScenariosTab scenarios={overview.scenarios} />
            </TabsContent>
            <TabsContent value="reasoning">
              <ReasoningTab traces={overview.traces} />
            </TabsContent>
            <TabsContent value="rejections">
              <RejectionsTab rejections={overview.rejections} />
            </TabsContent>
            <TabsContent value="execution">
              <ExecutionTab
                execution={overview.execution}
                alerts={overview.alerts}
                alertLog={alertLog}
              />
            </TabsContent>
          </Tabs>
        ) : null}

        {overview ? (
          <p className="mt-4 font-mono text-[10px] leading-4 text-muted-foreground" dir="auto">
            المصدر: {overview.composition_ref}
          </p>
        ) : null}
      </main>

      <footer className="mt-auto border-t border-border/60 bg-background">
        <div
          className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] text-[11px] text-muted-foreground"
          dir="auto"
        >
          <span>AI Market Reasoning Engine — MVP</span>
          <span className="font-mono">SIMULATION_ONLY (§28)</span>
          <span>لا يشكل توصية تداول</span>
          <span className="ms-auto font-mono">بوابات 0-9 مغلقة · بوابة 10 = MVP-DoD §51</span>
        </div>
      </footer>
    </div>
  );
}
