"use client";

import { ROLES } from "@deploymind/shared";
import { useQuery } from "@tanstack/react-query";
import { use } from "react";

import { KeyValue, PageHeader, QueryView } from "@/components/app/common";
import { JourneyView } from "@/components/domain/journey";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "@/components/ui";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/utils";

export default function OrganisationDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const org = useQuery({ queryKey: ["org", id], queryFn: () => api(`/organisations/${id}`) });
  const members = useQuery({ queryKey: ["members", id], queryFn: () => api<any[]>(`/organisations/${id}/members`) });
  const contacts = useQuery({ queryKey: ["contacts", id], queryFn: () => api<any[]>(`/organisations/${id}/contacts`) });
  return (
    <QueryView q={org}>
      {(o: any) => (
        <>
          <PageHeader title={o.name} back={{ href: "/app/organisations", label: "Organisations" }} description={`${o.industry ?? ""} · ${o.size ?? ""} employees`} />
          <div className="mb-6 grid gap-4 lg:grid-cols-3">
            <Card><CardHeader><CardTitle>Profile</CardTitle></CardHeader><CardContent><KeyValue items={[["Website", o.website], ["Country", o.country], ["Slug", o.slug], ["Description", o.description]]} /></CardContent></Card>
            <Card><CardHeader><CardTitle>Portal users</CardTitle></CardHeader><CardContent><QueryView q={members}>{(m) => (
              <ul className="space-y-2 text-sm">{m.map((u) => <li key={u.user_id} className="flex justify-between gap-2"><span>{u.full_name}<span className="block text-xs text-muted-foreground">{u.email} · {relativeTime(u.last_login_at)}</span></span><Badge>{ROLES[u.role as keyof typeof ROLES]}</Badge></li>)}</ul>)}
            </QueryView></CardContent></Card>
            <Card><CardHeader><CardTitle>Contacts</CardTitle></CardHeader><CardContent><QueryView q={contacts}>{(c) => (
              <ul className="space-y-2 text-sm">{c.map((x) => <li key={x.id}>{x.full_name}{x.is_primary && <Badge className="ml-2" tone="primary">Primary</Badge>}<span className="block text-xs text-muted-foreground">{x.job_title} · {x.email}</span></li>)}</ul>)}
            </QueryView></CardContent></Card>
          </div>
          <JourneyView orgId={id} base="/app" />
        </>
      )}
    </QueryView>
  );
}
