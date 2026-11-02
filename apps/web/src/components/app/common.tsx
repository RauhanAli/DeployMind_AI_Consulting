"use client";

import { label } from "@deploymind/shared";
import type { UseQueryResult } from "@tanstack/react-query";
import { AlertTriangle, Inbox } from "lucide-react";
import Link from "next/link";
import type * as React from "react";

import { Badge, Button, Card, CardContent, Skeleton } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

export function PageHeader({ title, description, actions, back }: {
  title: string; description?: React.ReactNode; actions?: React.ReactNode; back?: { href: string; label: string };
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0 space-y-1">
        {back && <Link href={back.href} className="text-sm text-muted-foreground hover:text-foreground">← {back.label}</Link>}
        <h1 className="truncate text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <div className="text-sm text-muted-foreground">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function StatCard({ label: l, value, hint, icon: Icon, tone }: {
  label: string; value: React.ReactNode; hint?: React.ReactNode; icon?: React.ComponentType<{ className?: string }>; tone?: "danger" | "success" | "warning";
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">{l}</p>
          {Icon && <Icon className={cn("size-4 text-muted-foreground", tone === "danger" && "text-danger", tone === "success" && "text-success")} />}
        </div>
        <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
        {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}

const TONES: Record<string, "neutral" | "primary" | "success" | "warning" | "danger"> = {
  // generic
  active: "success", healthy: "success", ready: "success", done: "success", completed: "success", approved: "success",
  accepted: "success", succeeded: "success", resolved: "success", closed: "neutral", reviewed: "success", met: "success",
  on_track: "success", selected: "success", configured: "primary",
  draft: "neutral", pending: "neutral", queued: "neutral", todo: "neutral", backlog: "neutral", identified: "neutral",
  inventory: "neutral", unknown: "neutral", not_deployed: "neutral", superseded: "neutral", stopped: "neutral", demo: "primary",
  in_progress: "primary", in_review: "primary", running: "primary", building: "primary", testing: "primary",
  releasing: "primary", processing: "primary", uploaded: "primary", sent: "primary", investigating: "warning", shortlisted: "primary",
  review: "primary", awaiting_approval: "warning", waiting_on_customer: "warning", at_risk: "warning", degraded: "warning",
  open: "warning", rolled_back: "warning", on_hold: "warning",
  failed: "danger", rejected: "danger", unhealthy: "danger", failing: "danger", breached: "danger", lost: "danger",
  cancelled: "neutral",
  sev1: "danger", sev2: "warning", sev3: "primary", sev4: "neutral", urgent: "danger", high: "warning", medium: "primary", low: "neutral",
  must: "danger", should: "warning", could: "neutral",
};

export function StatusBadge({ status, className }: { status?: string | null; className?: string }) {
  if (!status) return null;
  return <Badge tone={TONES[status] ?? "neutral"} className={className}>{label(status)}</Badge>;
}

export function EmptyState({ title, body, action, icon: Icon = Inbox }: {
  title: string; body?: string; action?: React.ReactNode; icon?: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed px-6 py-12 text-center">
      <Icon className="size-8 text-muted-foreground" />
      <p className="font-medium">{title}</p>
      {body && <p className="max-w-sm text-sm text-muted-foreground">{body}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-danger/30 bg-danger/5 p-4 text-sm" role="alert">
      <AlertTriangle className="mt-0.5 size-4 text-danger" />
      <div className="flex-1">
        <p className="font-medium text-danger">Could not load this data</p>
        <p className="text-muted-foreground">{errorMessage(error)}</p>
      </div>
      {retry && <Button size="sm" variant="outline" onClick={retry}>Retry</Button>}
    </div>
  );
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return <div className="space-y-3" aria-busy="true">{Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}</div>;
}

/** Renders loading / error / content states consistently for a TanStack query. */
export function QueryView<T>({ q, children, rows }: { q: UseQueryResult<T>; children: (data: T) => React.ReactNode; rows?: number }) {
  if (q.isPending) return <Loading rows={rows} />;
  if (q.isError) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  return <>{children(q.data as T)}</>;
}

export function KeyValue({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
      {items.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="text-xs text-muted-foreground">{k}</dt>
          <dd className="mt-0.5 break-words font-medium">{v ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function AiDraftNotice({ provenance, children }: { provenance?: any; children?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-xs">
      <Badge tone="warning">AI-generated draft</Badge>
      <span className="text-muted-foreground">
        {children ?? "Requires review by an authorised engineer. Not validated by virtue of being generated."}
        {provenance?.model && <> · {provenance.provider}:{provenance.model}{provenance.is_mock ? " (mock)" : ""}</>}
      </span>
    </div>
  );
}

export function MockBanner({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <div className="border-b border-warning/40 bg-warning/15 px-4 py-1.5 text-center text-xs">
      <strong>Mock AI mode:</strong> AI outputs come from deterministic local providers (no paid API keys). Configure OpenAI or Anthropic keys to use real models.
    </div>
  );
}
