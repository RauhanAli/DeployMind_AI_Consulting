"use client";

import { LEAD_PIPELINE, label } from "@deploymind/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { EmptyState, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { Badge, Button, Card, Dialog, DialogContent, Field, Input, Select, Table, Tabs, TabsContent, TabsList, TabsTrigger, Td, Textarea, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, money, relativeTime } from "@/lib/utils";

function NewLead() {
  const qc = useQueryClient();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ organisation_name: "", industry: "", title: "", estimated_value: "", summary: "" });
  const m = useMutation({ mutationFn: () => api("/crm/leads", { method: "POST", body: { ...f, estimated_value: f.estimated_value ? Number(f.estimated_value) : null } }),
    onSuccess: (l) => { qc.invalidateQueries({ queryKey: ["pipeline"] }); setOpen(false); router.push(`/app/crm/${l.id}`); }, onError: (e) => toast.error(errorMessage(e)) });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button onClick={() => setOpen(true)}>New lead</Button>
      <DialogContent title="New lead" description="Creates the customer organisation if it does not exist.">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
          <Field label="Organisation" htmlFor="l-org"><Input id="l-org" required minLength={2} value={f.organisation_name} onChange={(e) => setF({ ...f, organisation_name: e.target.value })} /></Field>
          <Field label="Industry" htmlFor="l-ind"><Input id="l-ind" value={f.industry} onChange={(e) => setF({ ...f, industry: e.target.value })} /></Field>
          <Field label="Opportunity title" htmlFor="l-title"><Input id="l-title" required minLength={2} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field label="Estimated value (GBP)" htmlFor="l-val"><Input id="l-val" type="number" min={0} value={f.estimated_value} onChange={(e) => setF({ ...f, estimated_value: e.target.value })} /></Field>
          <Field label="Summary" htmlFor="l-sum"><Textarea id="l-sum" value={f.summary} onChange={(e) => setF({ ...f, summary: e.target.value })} /></Field>
          <div className="flex justify-end"><Button type="submit" loading={m.isPending}>Create lead</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Calls() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["calls"], queryFn: () => api<any[]>("/crm/discovery-calls") });
  const patch = useMutation({ mutationFn: ({ id, status }: { id: string; status: string }) => api(`/crm/discovery-calls/${id}`, { method: "PATCH", body: { status } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["calls"] }), onError: (e) => toast.error(errorMessage(e)) });
  return (
    <QueryView q={q}>
      {(calls) => calls.length === 0 ? <EmptyState title="No bookings yet" /> : (
        <Card><Table><thead><tr><Th>Requested by</Th><Th>Type</Th><Th>Topic</Th><Th>Preferred slot</Th><Th>Status</Th></tr></thead><tbody>
          {calls.map((c) => (
            <tr key={c.id}>
              <Td><p className="font-medium">{c.full_name} · {c.company}</p><p className="text-xs text-muted-foreground">{c.email}</p>{c.message && <p className="mt-1 max-w-md text-xs">{c.message}</p>}</Td>
              <Td><Badge>{c.kind}</Badge></Td><Td>{c.topic}</Td><Td className="text-xs">{formatDateTime(c.preferred_slot)}<br /><span className="text-muted-foreground">{c.timezone}</span></Td>
              <Td><Select aria-label="Booking status" className="h-8 w-36" value={c.status} onChange={(e) => patch.mutate({ id: c.id, status: e.target.value })}>
                {["requested", "confirmed", "completed", "cancelled"].map((s) => <option key={s} value={s}>{label(s)}</option>)}</Select></Td>
            </tr>
          ))}
        </tbody></Table></Card>
      )}
    </QueryView>
  );
}

function CrmInner() {
  const { can } = useAuth();
  const params = useSearchParams();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const pipeline = useQuery({ queryKey: ["pipeline"], queryFn: () => api("/crm/pipeline") });
  const leads = useQuery({ queryKey: ["leads", q, status], queryFn: () => api(`/crm/leads?page_size=100${q ? `&q=${encodeURIComponent(q)}` : ""}${status ? `&status=${status}` : ""}`) });
  return (
    <>
      <PageHeader title="CRM" description="Leads move New → Qualified → Discovery → Assessment → Proposal → Approved → Implementation → Completed." actions={can("crm.write") && <NewLead />} />
      <Tabs defaultValue={params?.get("tab") ?? "pipeline"}>
        <TabsList><TabsTrigger value="pipeline">Pipeline</TabsTrigger><TabsTrigger value="list">Leads</TabsTrigger><TabsTrigger value="calls">Discovery calls</TabsTrigger></TabsList>
        <TabsContent value="pipeline">
          <QueryView q={pipeline}>
            {(p: any) => (
              <div className="flex gap-3 overflow-x-auto pb-2">
                {[...LEAD_PIPELINE, "lost"].map((s) => (
                  <div key={s} className="w-64 shrink-0 rounded-xl bg-muted/60 p-2">
                    <div className="flex items-center justify-between px-1 pb-2"><span className="text-xs font-semibold uppercase text-muted-foreground">{label(s)}</span><Badge>{p.columns[s]?.length ?? 0}</Badge></div>
                    <div className="space-y-2">
                      {(p.columns[s] ?? []).map((l: any) => (
                        <Link key={l.id} href={`/app/crm/${l.id}`} className="block rounded-lg border bg-card p-3 text-sm hover:border-primary/40">
                          <p className="font-medium">{l.organisation_name}</p><p className="text-xs text-muted-foreground">{l.title}</p>
                          <div className="mt-2 flex justify-between text-xs text-muted-foreground"><span>{money(l.estimated_value)}</span><span>{l.owner_name?.split(" ")[0]}</span></div>
                        </Link>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </QueryView>
        </TabsContent>
        <TabsContent value="list">
          <div className="mb-3 flex flex-wrap gap-2">
            <Input placeholder="Search leads or organisations…" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-xs" aria-label="Search leads" />
            <Select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)} className="w-48">
              <option value="">All statuses</option>{[...LEAD_PIPELINE, "lost"].map((s) => <option key={s} value={s}>{label(s)}</option>)}</Select>
          </div>
          <QueryView q={leads}>
            {(d: any) => d.items.length === 0 ? <EmptyState title="No leads match" /> : (
              <Card><Table><thead><tr><Th>Lead</Th><Th>Status</Th><Th>Source</Th><Th>Owner</Th><Th>Value</Th><Th>Updated</Th></tr></thead><tbody>
                {d.items.map((l: any) => (
                  <tr key={l.id} className="hover:bg-muted/40"><Td><Link href={`/app/crm/${l.id}`} className="font-medium hover:underline">{l.organisation_name}</Link><p className="text-xs text-muted-foreground">{l.title}</p></Td>
                    <Td><StatusBadge status={l.status} /></Td><Td>{label(l.source)}</Td><Td>{l.owner_name ?? "—"}</Td><Td>{money(l.estimated_value)}</Td><Td className="text-xs">{relativeTime(l.updated_at)}</Td></tr>
                ))}
              </tbody></Table></Card>
            )}
          </QueryView>
        </TabsContent>
        <TabsContent value="calls"><Calls /></TabsContent>
      </Tabs>
    </>
  );
}

export default function CrmPage() {
  return <Suspense><CrmInner /></Suspense>;
}
