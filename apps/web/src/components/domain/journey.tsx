"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Circle } from "lucide-react";
import Link from "next/link";

import { EmptyState, QueryView, StatusBadge } from "@/components/app/common";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui";
import { api } from "@/lib/api";
import { cn, formatDate, money, relativeTime } from "@/lib/utils";

export function JourneyView({ orgId, base }: { orgId: string; base: "/portal" | "/app" }) {
  const q = useQuery({ queryKey: ["journey", orgId], queryFn: () => api(`/organisations/${orgId}/journey`) });
  const link = (kind: string, id: string) => (base === "/portal" ? `/portal/${kind}/${id}` : `/app/${kind}/${id}`);
  return (
    <QueryView q={q} rows={6}>
      {(j: any) => (
        <div className="space-y-6">
          <Card>
            <CardContent className="p-5">
              <ol className="grid grid-cols-3 gap-3 sm:grid-cols-6">
                {j.stages.map((s: any, i: number) => (
                  <li key={s.key} className="flex flex-col items-center gap-2 text-center">
                    <span className={cn("flex size-9 items-center justify-center rounded-full border-2", s.done ? "border-success bg-success/10 text-success" : "border-border text-muted-foreground")}>
                      {s.done ? <CheckCircle2 className="size-5" /> : <Circle className="size-4" />}
                    </span>
                    <span className="text-xs font-medium">{i + 1}. {s.label}</span>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
          <div className="grid gap-4 lg:grid-cols-3">
            <Section title="Assessments" empty="No assessments yet">
              {j.assessments.map((a: any) => (
                <Row key={a.id} href={link("assessments", a.id)} title={a.overall_score ? `${a.overall_score}/100 · ${a.classification}` : "Draft assessment"}
                  meta={a.submitted_at ? formatDate(a.submitted_at) : "In progress"} status={a.status} />
              ))}
            </Section>
            <Section title="Proposals" empty="No proposals shared yet">
              {j.proposals.map((p: any) => (
                <Row key={p.id} href={link("proposals", p.id)} title={p.title} meta={money(p.total_estimate, p.currency)} status={p.status} />
              ))}
            </Section>
            <Section title="Projects" empty="No projects yet">
              {j.projects.map((p: any) => (
                <Row key={p.id} href={link("projects", p.id)} title={p.name} meta={`Target ${formatDate(p.target_date)}`} status={p.stage} />
              ))}
            </Section>
            <Section title="Top opportunities" empty="Complete an assessment to see opportunities">
              {j.opportunities.slice(0, 5).map((o: any) => (
                <Row key={o.id} title={`#${o.rank} ${o.title}`} meta={`Priority ${o.priority_score}`} status={o.status} />
              ))}
            </Section>
            <Section title="Deployments" empty="Nothing deployed yet">
              {j.deployments.slice(0, 5).map((d: any) => (
                <Row key={d.id} href={base === "/app" ? `/app/deployments/${d.id}` : undefined} title={d.version}
                  meta={`${relativeTime(d.created_at)}${d.is_demo ? " · demo record" : ""}`} status={d.status} />
              ))}
            </Section>
            <Section title="Incidents & support" empty="No incidents or tickets">
              {j.incidents.slice(0, 3).map((i: any) => <Row key={i.id} href={link("incidents", i.id)} title={`${i.code} ${i.title}`} meta={i.severity} status={i.status} />)}
              {j.tickets.slice(0, 3).map((t: any) => <Row key={t.id} href={link("support", t.id)} title={`${t.code} ${t.subject}`} meta={t.priority} status={t.status} />)}
            </Section>
          </div>
          <Card>
            <CardHeader><CardTitle>Activity</CardTitle></CardHeader>
            <CardContent>
              {j.activity.length === 0 ? <EmptyState title="No activity yet" /> : (
                <ul className="space-y-3">
                  {j.activity.map((a: any) => (
                    <li key={a.id} className="flex gap-3 text-sm">
                      <span className="mt-1.5 size-2 shrink-0 rounded-full bg-primary" />
                      <div><p>{a.message}</p><p className="text-xs text-muted-foreground">{a.actor_name ?? "System"} · {relativeTime(a.created_at)}</p></div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </QueryView>
  );
}

function Section({ title, empty, children }: { title: string; empty: string; children: React.ReactNode }) {
  const has = Array.isArray(children) ? children.flat().filter(Boolean).length > 0 : !!children;
  return (
    <Card>
      <CardHeader><CardTitle className="text-sm">{title}</CardTitle></CardHeader>
      <CardContent className="space-y-1">{has ? children : <p className="text-sm text-muted-foreground">{empty}</p>}</CardContent>
    </Card>
  );
}

function Row({ title, meta, status, href }: { title: string; meta?: string; status?: string; href?: string }) {
  const inner = (
    <div className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 hover:bg-muted">
      <div className="min-w-0"><p className="truncate text-sm font-medium">{title}</p>{meta && <p className="text-xs text-muted-foreground">{meta}</p>}</div>
      <StatusBadge status={status} />
    </div>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
}
