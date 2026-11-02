"use client";

import { label } from "@deploymind/shared";
import { useQuery } from "@tanstack/react-query";
import { Activity, Briefcase, Building2, DollarSign, FileText, LifeBuoy, PhoneCall, Rocket, ShieldAlert } from "lucide-react";
import Link from "next/link";

import { PageHeader, QueryView, StatCard, StatusBadge } from "@/components/app/common";
import { Card, CardContent, CardHeader, CardTitle, Progress } from "@/components/ui";
import { api } from "@/lib/api";
import { compact, relativeTime, usd } from "@/lib/utils";

const PIPE = ["new", "qualified", "discovery", "assessment", "proposal", "approved", "implementation", "completed"];

export default function Overview() {
  const q = useQuery({ queryKey: ["overview"], queryFn: () => api("/dashboard/overview"), refetchInterval: 30_000 });
  return (
    <>
      <PageHeader title="Overview" description="Live view of customers, delivery and operations — every figure is computed from persisted data." />
      <QueryView q={q} rows={6}>
        {(d: any) => (
          <div className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Customers" value={d.total_customers} icon={Building2} />
              <StatCard label="Active projects" value={d.active_projects} icon={Briefcase} />
              <StatCard label="Pending proposals" value={d.pending_proposals} icon={FileText} />
              <StatCard label="Deployments" value={d.deployments.total} hint={`${d.deployments.healthy} healthy · ${d.deployments.awaiting_approval} awaiting approval`} icon={Rocket} />
              <StatCard label="Open incidents" value={d.open_incidents} icon={ShieldAlert} tone={d.open_incidents ? "danger" : undefined} />
              <StatCard label="Open tickets" value={d.open_tickets} icon={LifeBuoy} />
              <StatCard label="AI usage this month" value={`${compact(d.ai_usage_month.requests)} req`} hint={`${compact(d.ai_usage_month.tokens)} tokens`} icon={Activity} />
              <StatCard label="Est. AI cost this month" value={usd(d.ai_usage_month.estimated_cost_usd)} hint="Includes labelled demo usage" icon={DollarSign} />
            </div>
            <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
              <Card>
                <CardHeader><CardTitle>Pipeline</CardTitle></CardHeader>
                <CardContent className="space-y-2">
                  {PIPE.map((s) => {
                    const n = d.pipeline[s] ?? 0;
                    const max = Math.max(1, ...Object.values(d.pipeline as Record<string, number>));
                    return (
                      <div key={s} className="grid grid-cols-[120px_1fr_32px] items-center gap-3 text-sm">
                        <span className="text-muted-foreground">{label(s)}</span><Progress value={(n / max) * 100} /><span className="text-right font-medium">{n}</span>
                      </div>
                    );
                  })}
                  {d.discovery_calls_requested > 0 && (
                    <Link href="/app/crm?tab=calls" className="mt-3 flex items-center gap-2 rounded-md bg-accent p-2 text-sm text-accent-foreground"><PhoneCall className="size-4" />{d.discovery_calls_requested} discovery call request(s) awaiting confirmation</Link>
                  )}
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle>Project completion</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                  <div><div className="mb-1 flex justify-between text-sm"><span>Tasks done</span><span>{d.task_completion.done}/{d.task_completion.total}</span></div><Progress value={d.task_completion.percent} tone="success" /></div>
                  {d.projects.map((p: any) => (
                    <Link key={p.id} href={`/app/projects/${p.id}`} className="flex items-center justify-between rounded-md p-2 text-sm hover:bg-muted"><span className="font-medium">{p.name}</span><StatusBadge status={p.stage} /></Link>
                  ))}
                </CardContent>
              </Card>
            </div>
            <Card>
              <CardHeader><CardTitle>Recent activity</CardTitle></CardHeader>
              <CardContent>
                <ul className="divide-y">
                  {d.recent_activity.map((a: any) => (
                    <li key={a.id} className="flex flex-wrap items-baseline justify-between gap-2 py-2.5 text-sm">
                      <span><span className="font-medium">{a.organisation}</span> · {a.message}</span>
                      <span className="text-xs text-muted-foreground">{a.actor ?? "System"} · {relativeTime(a.created_at)}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          </div>
        )}
      </QueryView>
    </>
  );
}
