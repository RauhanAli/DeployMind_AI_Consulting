"use client";

import { INCIDENT_FLOW, TICKET_FLOW, label } from "@deploymind/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { AiDraftNotice, EmptyState, KeyValue, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Dialog, DialogContent, Field, Input, Select, Table, Td, Textarea, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, formatDateTime, relativeTime } from "@/lib/utils";

// ---------------------------------------------------------------- Support
export function TicketList({ base, orgId }: { base: "/app" | "/portal"; orgId?: string }) {
  const [status, setStatus] = useState("");
  const q = useQuery({ queryKey: ["tickets", status, orgId], queryFn: () => api(`/support/tickets?page_size=50${status ? `&status=${status}` : ""}${orgId ? `&organisation_id=${orgId}` : ""}`) });
  return (
    <>
      <div className="mb-3 flex gap-2">
        <Select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)} className="w-56">
          <option value="">All statuses</option>
          <option value="open,in_progress,waiting_on_customer">Open (any)</option>
          {Object.keys(TICKET_FLOW).map((s) => <option key={s} value={s}>{label(s)}</option>)}
        </Select>
      </div>
      <QueryView q={q}>
        {(d: any) => d.items.length === 0 ? <EmptyState title="No tickets" /> : (
          <Card><Table><thead><tr><Th>Ticket</Th>{base === "/app" && <Th>Organisation</Th>}<Th>Priority</Th><Th>Status</Th><Th>Response SLA</Th><Th>Resolution SLA</Th><Th>Opened</Th></tr></thead><tbody>
            {d.items.map((t: any) => (
              <tr key={t.id} className="hover:bg-muted/40">
                <Td><Link href={`${base}/support/${t.id}`} className="font-medium hover:underline">{t.code} · {t.subject}</Link></Td>
                {base === "/app" && <Td>{t.organisation_name}</Td>}
                <Td><StatusBadge status={t.priority} /></Td><Td><StatusBadge status={t.status} /></Td>
                <Td><StatusBadge status={t.sla_response} /></Td><Td><StatusBadge status={t.sla_resolution} /></Td>
                <Td className="text-xs">{relativeTime(t.created_at)}</Td>
              </tr>
            ))}
          </tbody></Table></Card>
        )}
      </QueryView>
    </>
  );
}

export function NewTicketButton({ orgId, projects }: { orgId?: string; projects?: any[] }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ subject: "", description: "", priority: "medium", category: "general", project_id: "" });
  const m = useMutation({
    mutationFn: () => api("/support/tickets", { method: "POST", body: { ...form, project_id: form.project_id || null, organisation_id: orgId } }),
    onSuccess: () => { toast.success("Ticket created"); setOpen(false); setForm({ subject: "", description: "", priority: "medium", category: "general", project_id: "" }); qc.invalidateQueries({ queryKey: ["tickets"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const valid = form.subject.trim().length >= 3 && form.description.trim().length >= 3;
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button onClick={() => setOpen(true)}><Plus /> New ticket</Button>
      <DialogContent title="Raise a support ticket" description="Response and resolution targets are set by priority.">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (valid) m.mutate(); }}>
          <Field label="Subject" htmlFor="tk-subject"><Input id="tk-subject" value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} /></Field>
          <Field label="Description" htmlFor="tk-desc"><Textarea id="tk-desc" rows={5} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Priority" htmlFor="tk-prio"><Select id="tk-prio" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
              {["low", "medium", "high", "urgent"].map((p) => <option key={p} value={p}>{label(p)}</option>)}</Select></Field>
            <Field label="Category" htmlFor="tk-cat"><Select id="tk-cat" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {["general", "bug", "question", "feature_request", "access", "billing"].map((p) => <option key={p} value={p}>{label(p)}</option>)}</Select></Field>
          </div>
          {projects && projects.length > 0 && (
            <Field label="Project (optional)" htmlFor="tk-proj"><Select id="tk-proj" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
              <option value="">None</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
          )}
          <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" loading={m.isPending} disabled={!valid}>Create ticket</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function TicketDetail({ id, area }: { id: string; area: "portal" | "internal" }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const t = useQuery({ queryKey: ["ticket", id], queryFn: () => api(`/support/tickets/${id}`) });
  const comments = useQuery({ queryKey: ["ticket-comments", id], queryFn: () => api<any[]>(`/support/tickets/${id}/comments`) });
  const staff = useQuery({ queryKey: ["staff"], queryFn: () => api<any[]>("/users/staff"), enabled: area === "internal" });
  const [body, setBody] = useState("");
  const [internal, setInternal] = useState(false);
  const [resolution, setResolution] = useState("");
  const inv = () => { qc.invalidateQueries({ queryKey: ["ticket", id] }); qc.invalidateQueries({ queryKey: ["ticket-comments", id] }); qc.invalidateQueries({ queryKey: ["tickets"] }); };
  const patch = useMutation({ mutationFn: (b: any) => api(`/support/tickets/${id}`, { method: "PATCH", body: b }), onSuccess: inv, onError: (e) => toast.error(errorMessage(e)) });
  const comment = useMutation({ mutationFn: () => api(`/support/tickets/${id}/comments`, { method: "POST", body: { body, internal } }),
    onSuccess: () => { setBody(""); inv(); }, onError: (e) => toast.error(errorMessage(e)) });
  const manage = area === "internal" && can("support.manage");

  return (
    <QueryView q={t} rows={5}>
      {(tk: any) => (
        <>
          <PageHeader title={`${tk.code} · ${tk.subject}`} back={{ href: area === "portal" ? "/portal/support" : "/app/support", label: "Support" }}
            description={<span className="flex flex-wrap gap-2"><StatusBadge status={tk.status} /><StatusBadge status={tk.priority} /><Badge>{label(tk.category)}</Badge></span>} />
          <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
            <div className="space-y-4">
              <Card><CardContent className="p-5"><p className="whitespace-pre-wrap text-sm">{tk.description}</p><p className="mt-2 text-xs text-muted-foreground">{tk.requester_name} · {formatDateTime(tk.created_at)}</p></CardContent></Card>
              <QueryView q={comments}>
                {(list) => (
                  <div className="space-y-3">
                    {list.map((c) => (
                      <div key={c.id} className={cn("rounded-xl border bg-card p-4 text-sm", c.internal && "border-dashed bg-muted/50")}>
                        <p className="mb-1 text-xs text-muted-foreground">{c.author_name ?? "System"} · {relativeTime(c.created_at)} {c.internal && <Badge className="ml-1">Internal</Badge>}</p>
                        <p className="whitespace-pre-wrap">{c.body}</p>
                      </div>
                    ))}
                  </div>
                )}
              </QueryView>
              {tk.status !== "closed" && can("support.write") && (
                <Card><CardContent className="space-y-2 p-4">
                  <Textarea placeholder="Write a reply…" value={body} onChange={(e) => setBody(e.target.value)} aria-label="Reply" />
                  <div className="flex items-center justify-between">
                    {area === "internal" ? <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} /> Internal note (hidden from customer)</label> : <span />}
                    <Button size="sm" onClick={() => comment.mutate()} loading={comment.isPending} disabled={!body.trim()}>Send</Button>
                  </div>
                </CardContent></Card>
              )}
            </div>
            <div className="space-y-4">
              <Card>
                <CardHeader><CardTitle>Details</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                  <KeyValue items={[["Response due", formatDateTime(tk.response_due_at)], ["Response SLA", <StatusBadge key="r" status={tk.sla_response} />],
                    ["Resolution due", formatDateTime(tk.resolution_due_at)], ["Resolution SLA", <StatusBadge key="s" status={tk.sla_resolution} />],
                    ["First response", formatDateTime(tk.first_response_at)], ["Assignee", tk.assignee_name ?? "Unassigned"]]} />
                  {tk.resolution_notes && <div className="rounded-md bg-success/10 p-3 text-sm"><p className="text-xs font-medium">Resolution</p>{tk.resolution_notes}</div>}
                </CardContent>
              </Card>
              {manage && (
                <Card>
                  <CardHeader><CardTitle>Manage</CardTitle></CardHeader>
                  <CardContent className="space-y-3">
                    <Field label="Assignee" htmlFor="tk-assignee"><Select id="tk-assignee" value={tk.assignee_id ?? ""} onChange={(e) => patch.mutate({ assignee_id: e.target.value || null })}>
                      <option value="">Unassigned</option>{(staff.data ?? []).map((s) => <option key={s.user_id} value={s.user_id}>{s.full_name}</option>)}</Select></Field>
                    <Field label="Priority" htmlFor="tk-p"><Select id="tk-p" value={tk.priority} onChange={(e) => patch.mutate({ priority: e.target.value })}>
                      {["low", "medium", "high", "urgent"].map((p) => <option key={p} value={p}>{label(p)}</option>)}</Select></Field>
                    {(TICKET_FLOW[tk.status] ?? []).includes("resolved") && (
                      <Field label="Resolution notes" htmlFor="tk-res"><Textarea id="tk-res" value={resolution} onChange={(e) => setResolution(e.target.value)} /></Field>
                    )}
                    <div className="flex flex-wrap gap-2">
                      {(TICKET_FLOW[tk.status] ?? []).map((s) => (
                        <Button key={s} size="sm" variant={s === "resolved" ? "default" : "outline"} loading={patch.isPending}
                          disabled={s === "resolved" && !resolution.trim() && !tk.resolution_notes}
                          onClick={() => patch.mutate(s === "resolved" ? { status: s, resolution_notes: resolution || tk.resolution_notes } : { status: s })}>{label(s)}</Button>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
              {area === "portal" && tk.status === "resolved" && (
                <Card><CardContent className="flex flex-wrap gap-2 p-4">
                  <Button size="sm" onClick={() => patch.mutate({ status: "closed" })}>Confirm resolved</Button>
                  <Button size="sm" variant="outline" onClick={() => patch.mutate({ status: "in_progress" })}>Reopen</Button>
                </CardContent></Card>
              )}
            </div>
          </div>
        </>
      )}
    </QueryView>
  );
}

// ---------------------------------------------------------------- Incidents
export function IncidentDetail({ id, area }: { id: string; area: "portal" | "internal" }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const write = area === "internal" && can("incident.write");
  const inc = useQuery({ queryKey: ["incident", id], queryFn: () => api(`/incidents/${id}`) });
  const updates = useQuery({ queryKey: ["incident-updates", id], queryFn: () => api<any[]>(`/incidents/${id}/updates`) });
  const staff = useQuery({ queryKey: ["staff"], queryFn: () => api<any[]>("/users/staff"), enabled: write });
  const [msg, setMsg] = useState("");
  const [notifyCustomer, setNotifyCustomer] = useState(true);
  const [note, setNote] = useState("");
  const [publicNote, setPublicNote] = useState(false);
  const [rca, setRca] = useState<{ root_cause?: string; resolution?: string }>({});
  const inv = () => { qc.invalidateQueries({ queryKey: ["incident", id] }); qc.invalidateQueries({ queryKey: ["incident-updates", id] }); qc.invalidateQueries({ queryKey: ["incidents"] }); };
  const status = useMutation({ mutationFn: (s: string) => api(`/incidents/${id}/status`, { method: "POST", body: { status: s, message: msg || `Status changed to ${s}`, notify_customer: notifyCustomer } }),
    onSuccess: () => { setMsg(""); inv(); toast.success("Status updated"); }, onError: (e) => toast.error(errorMessage(e)) });
  const patch = useMutation({ mutationFn: (b: any) => api(`/incidents/${id}`, { method: "PATCH", body: b }), onSuccess: () => { inv(); toast.success("Saved"); }, onError: (e) => toast.error(errorMessage(e)) });
  const addNote = useMutation({ mutationFn: () => api(`/incidents/${id}/updates`, { method: "POST", body: { message: note, public: publicNote } }),
    onSuccess: () => { setNote(""); inv(); }, onError: (e) => toast.error(errorMessage(e)) });
  const analyze = useMutation({ mutationFn: () => api(`/incidents/${id}/analyze`, { method: "POST" }), onSuccess: inv, onError: (e) => toast.error(errorMessage(e)) });

  return (
    <QueryView q={inc} rows={5}>
      {(i: any) => (
        <>
          <PageHeader title={`${i.code} · ${i.title}`} back={{ href: area === "portal" ? "/portal/incidents" : "/app/incidents", label: "Incidents" }}
            description={<span className="flex flex-wrap gap-2"><StatusBadge status={i.severity} /><StatusBadge status={i.status} /> {i.organisation_name} · detected {formatDateTime(i.detected_at)}</span>}
            actions={write && <Button variant="outline" onClick={() => analyze.mutate()} loading={analyze.isPending}><Sparkles /> AI analysis</Button>} />
          <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
            <div className="space-y-4">
              {area === "internal" && i.description && <Card><CardContent className="p-5 text-sm">{i.description}</CardContent></Card>}
              {i.ai_analysis?.summary && (
                <Card>
                  <CardHeader><CardTitle>AI incident analysis</CardTitle><AiDraftNotice provenance={i.ai_analysis.provenance}>Advisory only — engineers decide and act.</AiDraftNotice></CardHeader>
                  <CardContent className="grid gap-4 text-sm md:grid-cols-2">
                    <div><p className="font-medium">Likely causes</p><ul className="list-disc pl-5 text-muted-foreground">{i.ai_analysis.likely_causes.map((c: string) => <li key={c}>{c}</li>)}</ul></div>
                    <div><p className="font-medium">Suggested actions</p><ul className="list-disc pl-5 text-muted-foreground">{i.ai_analysis.suggested_actions.map((c: string) => <li key={c}>{c}</li>)}</ul></div>
                    <div className="md:col-span-2"><p className="font-medium">Evidence</p><ul className="list-disc pl-5 text-muted-foreground">{i.ai_analysis.evidence.map((c: string) => <li key={c}>{c}</li>)}</ul></div>
                    <div className="md:col-span-2 rounded-md bg-muted p-3"><p className="text-xs font-medium">Draft customer update</p><p>{i.ai_analysis.customer_update_draft}</p>
                      {write && <Button size="sm" variant="link" onClick={() => setMsg(i.ai_analysis.customer_update_draft)}>Use as status message</Button>}</div>
                  </CardContent>
                </Card>
              )}
              <Card>
                <CardHeader><CardTitle>Timeline</CardTitle></CardHeader>
                <CardContent>
                  <QueryView q={updates}>
                    {(list) => list.length === 0 ? <p className="text-sm text-muted-foreground">No public updates yet.</p> : (
                      <ol className="relative space-y-4 border-l pl-6">
                        {list.map((u) => (
                          <li key={u.id}>
                            <span className={cn("absolute -left-1.5 mt-1.5 size-3 rounded-full border-2 border-card", u.public ? "bg-primary" : "bg-muted-foreground")} />
                            <p className="flex flex-wrap items-center gap-2 text-sm">{u.status && <StatusBadge status={u.status} />}{u.message}</p>
                            <p className="text-xs text-muted-foreground">{u.author_name ?? "DeployMind"} · {formatDateTime(u.created_at)} {area === "internal" && (u.public ? "· shared with customer" : "· internal")}</p>
                          </li>
                        ))}
                      </ol>
                    )}
                  </QueryView>
                </CardContent>
              </Card>
              {write && (
                <Card><CardContent className="space-y-2 p-4">
                  <Textarea placeholder="Add an investigation note or customer update…" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Incident note" />
                  <div className="flex items-center justify-between">
                    <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={publicNote} onChange={(e) => setPublicNote(e.target.checked)} /> Send to customer</label>
                    <Button size="sm" onClick={() => addNote.mutate()} disabled={note.trim().length < 2} loading={addNote.isPending}>Post</Button>
                  </div>
                </CardContent></Card>
              )}
            </div>
            <div className="space-y-4">
              <Card>
                <CardHeader><CardTitle>Summary</CardTitle></CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <KeyValue items={[["Identified", formatDateTime(i.identified_at)], ["Resolved", formatDateTime(i.resolved_at)], ["Closed", formatDateTime(i.closed_at)], ["Assignee", i.assignee_name ?? "—"]]} />
                  {i.customer_impact && <div><p className="text-xs text-muted-foreground">Customer impact</p><p>{i.customer_impact}</p></div>}
                  {i.root_cause && <div><p className="text-xs text-muted-foreground">Root cause</p><p>{i.root_cause}</p></div>}
                  {i.resolution && <div><p className="text-xs text-muted-foreground">Resolution</p><p>{i.resolution}</p></div>}
                </CardContent>
              </Card>
              {write && (
                <>
                  <Card>
                    <CardHeader><CardTitle>Change status</CardTitle></CardHeader>
                    <CardContent className="space-y-3">
                      <Textarea placeholder="Status message" value={msg} onChange={(e) => setMsg(e.target.value)} aria-label="Status message" />
                      <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={notifyCustomer} onChange={(e) => setNotifyCustomer(e.target.checked)} /> Notify customer</label>
                      <div className="flex flex-wrap gap-2">
                        {(INCIDENT_FLOW[i.status] ?? []).map((s) => <Button key={s} size="sm" variant="outline" onClick={() => status.mutate(s)} loading={status.isPending && status.variables === s}>{label(s)}</Button>)}
                        {(INCIDENT_FLOW[i.status] ?? []).length === 0 && <p className="text-xs text-muted-foreground">Incident is closed.</p>}
                      </div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader><CardTitle>Post-incident</CardTitle></CardHeader>
                    <CardContent className="space-y-3">
                      <Field label="Assignee" htmlFor="inc-assignee"><Select id="inc-assignee" value={i.assignee_id ?? ""} onChange={(e) => patch.mutate({ assignee_id: e.target.value || null })}>
                        <option value="">Unassigned</option>{(staff.data ?? []).map((s) => <option key={s.user_id} value={s.user_id}>{s.full_name}</option>)}</Select></Field>
                      <Field label="Root cause" htmlFor="inc-rc"><Textarea id="inc-rc" defaultValue={i.root_cause ?? ""} onChange={(e) => setRca({ ...rca, root_cause: e.target.value })} /></Field>
                      <Field label="Resolution" htmlFor="inc-res"><Textarea id="inc-res" defaultValue={i.resolution ?? ""} onChange={(e) => setRca({ ...rca, resolution: e.target.value })} /></Field>
                      <Button size="sm" onClick={() => patch.mutate(rca)} disabled={!Object.keys(rca).length} loading={patch.isPending}>Save</Button>
                    </CardContent>
                  </Card>
                </>
              )}
            </div>
          </div>
        </>
      )}
    </QueryView>
  );
}

export function IncidentList({ base }: { base: "/app" | "/portal" }) {
  const [status, setStatus] = useState("");
  const q = useQuery({ queryKey: ["incidents", status], queryFn: () => api(`/incidents?page_size=50${status ? `&status=${status}` : ""}`) });
  return (
    <>
      <div className="mb-3"><Select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)} className="w-56">
        <option value="">All statuses</option><option value="open,investigating,identified">Active</option>
        {Object.keys(INCIDENT_FLOW).map((s) => <option key={s} value={s}>{label(s)}</option>)}</Select></div>
      <QueryView q={q}>
        {(d: any) => d.items.length === 0 ? <EmptyState title="No incidents" body="Good news — nothing to report." /> : (
          <Card><Table><thead><tr><Th>Incident</Th>{base === "/app" && <Th>Organisation</Th>}<Th>Severity</Th><Th>Status</Th><Th>Detected</Th><Th>Resolved</Th></tr></thead><tbody>
            {d.items.map((i: any) => (
              <tr key={i.id} className="hover:bg-muted/40">
                <Td><Link href={`${base}/incidents/${i.id}`} className="font-medium hover:underline">{i.code} · {i.title}</Link></Td>
                {base === "/app" && <Td>{i.organisation_name}</Td>}
                <Td><StatusBadge status={i.severity} /></Td><Td><StatusBadge status={i.status} /></Td>
                <Td className="text-xs">{formatDateTime(i.detected_at)}</Td><Td className="text-xs">{formatDateTime(i.resolved_at)}</Td>
              </tr>
            ))}
          </tbody></Table></Card>
        )}
      </QueryView>
    </>
  );
}
