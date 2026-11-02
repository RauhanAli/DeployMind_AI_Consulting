"use client";

import { LEAD_PIPELINE, label } from "@deploymind/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";
import { toast } from "sonner";

import { KeyValue, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Field, Input, Select, Textarea } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { money, relativeTime } from "@/lib/utils";

export default function LeadDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const qc = useQueryClient();
  const { can } = useAuth();
  const lead = useQuery({ queryKey: ["lead", id], queryFn: () => api(`/crm/leads/${id}`) });
  const acts = useQuery({ queryKey: ["lead-acts", id], queryFn: () => api<any[]>(`/crm/leads/${id}/activities`) });
  const staff = useQuery({ queryKey: ["staff"], queryFn: () => api<any[]>("/users/staff") });
  const orgId = lead.data?.organisation_id;
  const contacts = useQuery({ queryKey: ["contacts", orgId], queryFn: () => api<any[]>(`/organisations/${orgId}/contacts`), enabled: !!orgId });
  const [note, setNote] = useState("");
  const [kind, setKind] = useState("note");
  const [contact, setContact] = useState({ full_name: "", email: "", job_title: "" });
  const inv = () => { qc.invalidateQueries({ queryKey: ["lead", id] }); qc.invalidateQueries({ queryKey: ["lead-acts", id] }); qc.invalidateQueries({ queryKey: ["pipeline"] }); };
  const status = useMutation({ mutationFn: (s: string) => api(`/crm/leads/${id}/status`, { method: "POST", body: { status: s } }), onSuccess: inv, onError: (e) => toast.error(errorMessage(e)) });
  const patch = useMutation({ mutationFn: (b: any) => api(`/crm/leads/${id}`, { method: "PATCH", body: b }), onSuccess: inv, onError: (e) => toast.error(errorMessage(e)) });
  const addNote = useMutation({ mutationFn: () => api(`/crm/leads/${id}/notes`, { method: "POST", body: { body: note, kind } }), onSuccess: () => { setNote(""); inv(); }, onError: (e) => toast.error(errorMessage(e)) });
  const addContact = useMutation({ mutationFn: () => api(`/organisations/${orgId}/contacts`, { method: "POST", body: { ...contact, email: contact.email || null } }),
    onSuccess: () => { setContact({ full_name: "", email: "", job_title: "" }); qc.invalidateQueries({ queryKey: ["contacts", orgId] }); }, onError: (e) => toast.error(errorMessage(e)) });

  return (
    <QueryView q={lead}>
      {(l: any) => {
        const idx = LEAD_PIPELINE.indexOf(l.status as any);
        const next = LEAD_PIPELINE[idx + 1];
        return (
          <>
            <PageHeader title={l.organisation_name} back={{ href: "/app/crm", label: "CRM" }} description={<span className="flex items-center gap-2"><StatusBadge status={l.status} /> {l.title}</span>}
              actions={can("crm.write") && <>
                <Button variant="outline" asChild><Link href={`/app/organisations/${l.organisation_id}`}>Organisation journey</Link></Button>
                {l.status !== "lost" && l.status !== "completed" && <Button variant="ghost" onClick={() => status.mutate("lost")}>Mark lost</Button>}
                {next && l.status !== "lost" && <Button onClick={() => status.mutate(next)} loading={status.isPending}>Move to {label(next)}</Button>}
                {l.status === "lost" && <Button onClick={() => status.mutate("qualified")}>Re-open</Button>}
              </>} />
            <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
              <div className="space-y-4">
                {can("crm.write") && (
                  <Card><CardContent className="space-y-2 p-4">
                    <Textarea placeholder="Log a note, call or email…" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Activity note" />
                    <div className="flex justify-between gap-2">
                      <Select aria-label="Activity type" value={kind} onChange={(e) => setKind(e.target.value)} className="w-36">{["note", "call", "email", "meeting"].map((k) => <option key={k} value={k}>{label(k)}</option>)}</Select>
                      <Button onClick={() => addNote.mutate()} disabled={!note.trim()} loading={addNote.isPending}>Add to timeline</Button>
                    </div>
                  </CardContent></Card>
                )}
                <Card><CardHeader><CardTitle>Activity timeline</CardTitle></CardHeader><CardContent>
                  <QueryView q={acts}>{(list) => (
                    <ol className="relative space-y-4 border-l pl-6">
                      {list.map((a) => (
                        <li key={a.id}><span className="absolute -left-1.5 mt-1.5 size-3 rounded-full border-2 border-card bg-primary" />
                          <p className="text-sm"><Badge className="mr-2">{a.kind}</Badge>{a.message}</p>
                          <p className="text-xs text-muted-foreground">{a.actor_name ?? "System"} · {relativeTime(a.created_at)} · {a.entity_type}</p></li>
                      ))}
                    </ol>)}
                  </QueryView>
                </CardContent></Card>
              </div>
              <div className="space-y-4">
                <Card><CardHeader><CardTitle>Details</CardTitle></CardHeader><CardContent className="space-y-4">
                  <KeyValue items={[["Source", label(l.source)], ["Estimated value", money(l.estimated_value)], ["Status changed", relativeTime(l.status_changed_at)], ["Created", relativeTime(l.created_at)]]} />
                  {l.summary && <p className="text-sm text-muted-foreground">{l.summary}</p>}
                  <Field label="Owner" htmlFor="owner"><Select id="owner" disabled={!can("crm.write")} value={l.owner_id ?? ""} onChange={(e) => patch.mutate({ owner_id: e.target.value || null })}>
                    <option value="">Unassigned</option>{(staff.data ?? []).map((s) => <option key={s.user_id} value={s.user_id}>{s.full_name}</option>)}</Select></Field>
                </CardContent></Card>
                <Card><CardHeader><CardTitle>Contacts</CardTitle></CardHeader><CardContent className="space-y-3">
                  <QueryView q={contacts}>{(c) => <ul className="space-y-2 text-sm">{c.map((x) => <li key={x.id}>{x.full_name}{x.is_primary && <Badge tone="primary" className="ml-2">Primary</Badge>}<span className="block text-xs text-muted-foreground">{x.job_title} {x.email && `· ${x.email}`}</span></li>)}</ul>}</QueryView>
                  {can("crm.write") && (
                    <form className="space-y-2 border-t pt-3" onSubmit={(e) => { e.preventDefault(); addContact.mutate(); }}>
                      <Input placeholder="Name" required minLength={2} value={contact.full_name} onChange={(e) => setContact({ ...contact, full_name: e.target.value })} aria-label="Contact name" />
                      <Input placeholder="Email" type="email" value={contact.email} onChange={(e) => setContact({ ...contact, email: e.target.value })} aria-label="Contact email" />
                      <Input placeholder="Job title" value={contact.job_title} onChange={(e) => setContact({ ...contact, job_title: e.target.value })} aria-label="Contact job title" />
                      <Button size="sm" type="submit" loading={addContact.isPending}>Add contact</Button>
                    </form>
                  )}
                </CardContent></Card>
              </div>
            </div>
          </>
        );
      }}
    </QueryView>
  );
}
