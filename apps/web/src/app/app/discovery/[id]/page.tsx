"use client";

import { label } from "@deploymind/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Network, Plus, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { toast } from "sonner";

import { AiDraftNotice, EmptyState, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Dialog, DialogContent, Field, Input, Select, Table, Tabs, TabsContent, TabsList, TabsTrigger, Td, Textarea, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/utils";

export default function DiscoveryWorkspace({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const qc = useQueryClient();
  const router = useRouter();
  const { can } = useAuth();
  const s = useQuery({ queryKey: ["session", id], queryFn: () => api(`/discovery/sessions/${id}`) });
  const fields = useQuery({ queryKey: ["discovery-fields"], queryFn: () => api<Record<string, string>>("/discovery/fields") });
  const reqs = useQuery({ queryKey: ["reqs", id], queryFn: () => api<any[]>(`/requirements?session_id=${id}`) });
  const archs = useQuery({ queryKey: ["archs", id], queryFn: () => api<any[]>(`/architecture?session_id=${id}`) });
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState({ technical_notes: "", meeting_notes: "" });
  const [dirty, setDirty] = useState(false);
  useEffect(() => { if (s.data && !dirty) { setAnswers(s.data.answers); setNotes({ technical_notes: s.data.technical_notes, meeting_notes: s.data.meeting_notes }); } }, [s.data, dirty]);
  const write = can("discovery.write") && s.data?.status !== "completed";
  const inv = () => { qc.invalidateQueries({ queryKey: ["session", id] }); qc.invalidateQueries({ queryKey: ["reqs", id] }); qc.invalidateQueries({ queryKey: ["archs", id] }); };
  const save = useMutation({ mutationFn: () => api(`/discovery/sessions/${id}`, { method: "PATCH", body: { answers, ...notes } }),
    onSuccess: () => { setDirty(false); toast.success("Saved"); inv(); }, onError: (e) => toast.error(errorMessage(e)) });
  const analyze = useMutation({ mutationFn: async () => { if (dirty) await save.mutateAsync(); return api(`/discovery/sessions/${id}/analyze`, { method: "POST" }); },
    onSuccess: () => { toast.success("Discovery assistant finished"); inv(); }, onError: (e) => toast.error(errorMessage(e)) });
  const importReqs = useMutation({ mutationFn: (indexes: number[] | null) => api(`/discovery/sessions/${id}/import-requirements`, { method: "POST", body: { indexes } }),
    onSuccess: (r) => { toast.success(`${r.length} draft requirement(s) added — review and approve them`); inv(); }, onError: (e) => toast.error(errorMessage(e)) });
  const complete = useMutation({ mutationFn: (reopen: boolean) => api(`/discovery/sessions/${id}/${reopen ? "reopen" : "complete"}`, { method: "POST" }), onSuccess: inv, onError: (e) => toast.error(errorMessage(e)) });
  const genArch = useMutation({ mutationFn: () => api("/architecture/generate", { method: "POST", body: { session_id: id } }),
    onSuccess: (a) => router.push(`/app/architecture/${a.id}`), onError: (e) => toast.error(errorMessage(e)) });

  return (
    <QueryView q={s} rows={6}>
      {(sess: any) => {
        const ai = sess.ai_analysis ?? {};
        const approved = (reqs.data ?? []).filter((r) => r.status === "approved").length;
        return (
          <>
            <PageHeader title={sess.title} back={{ href: "/app/discovery", label: "Discovery" }}
              description={<span className="flex flex-wrap items-center gap-2"><StatusBadge status={sess.status} />{sess.organisation_name} · {formatDate(sess.session_date)} · owner {sess.owner_name}</span>}
              actions={<>
                {write && <Button variant="outline" onClick={() => save.mutate()} loading={save.isPending} disabled={!dirty}>Save</Button>}
                {write && <Button variant="outline" onClick={() => analyze.mutate()} loading={analyze.isPending}><Sparkles /> Run discovery assistant</Button>}
                {can("discovery.write") && <Button variant="ghost" onClick={() => complete.mutate(sess.status === "completed")}>{sess.status === "completed" ? "Reopen" : "Mark complete"}</Button>}
                {can("architecture.write") && <Button onClick={() => genArch.mutate()} loading={genArch.isPending} disabled={!approved} title={!approved ? "Approve at least one requirement first" : undefined}><Network /> Generate architecture</Button>}
              </>} />
            <Tabs defaultValue="questionnaire">
              <TabsList>
                <TabsTrigger value="questionnaire">Questionnaire</TabsTrigger>
                <TabsTrigger value="assistant">AI assistant {ai.summary && <Badge tone="primary" className="ml-1">ready</Badge>}</TabsTrigger>
                <TabsTrigger value="requirements">Requirements ({approved}/{reqs.data?.length ?? 0})</TabsTrigger>
                <TabsTrigger value="people">Stakeholders & actions</TabsTrigger>
                <TabsTrigger value="integrations">Integrations</TabsTrigger>
                <TabsTrigger value="architecture">Architecture ({archs.data?.length ?? 0})</TabsTrigger>
              </TabsList>
              <TabsContent value="questionnaire">
                <div className="grid gap-4 lg:grid-cols-2">
                  {Object.entries(fields.data ?? {}).map(([k, l]) => (
                    <Field key={k} label={l} htmlFor={`f-${k}`}>
                      <Textarea id={`f-${k}`} rows={3} disabled={!write} value={answers[k] ?? ""} onChange={(e) => { setAnswers({ ...answers, [k]: e.target.value }); setDirty(true); }} />
                    </Field>
                  ))}
                  <Field label="Technical notes" htmlFor="tn"><Textarea id="tn" rows={5} disabled={!write} value={notes.technical_notes} onChange={(e) => { setNotes({ ...notes, technical_notes: e.target.value }); setDirty(true); }} /></Field>
                  <Field label="Meeting notes" htmlFor="mn"><Textarea id="mn" rows={5} disabled={!write} value={notes.meeting_notes} onChange={(e) => { setNotes({ ...notes, meeting_notes: e.target.value }); setDirty(true); }} /></Field>
                </div>
              </TabsContent>
              <TabsContent value="assistant">
                {!ai.summary ? <EmptyState icon={Sparkles} title="Run the discovery assistant" body="It summarises notes, flags missing information, writes follow-up questions, identifies risks and proposes requirements for your review." /> : (
                  <div className="space-y-4">
                    <AiDraftNotice provenance={ai.provenance}>Suggestions only. Requirements are created as drafts and must be approved by an engineer.</AiDraftNotice>
                    <Card><CardHeader><CardTitle>Summary</CardTitle></CardHeader><CardContent className="text-sm">{ai.summary}</CardContent></Card>
                    <div className="grid gap-4 lg:grid-cols-2">
                      <Card><CardHeader><CardTitle>Missing information</CardTitle></CardHeader><CardContent>{ai.missing_information.length ? <ul className="list-disc pl-5 text-sm">{ai.missing_information.map((m: string) => <li key={m}>{m}</li>)}</ul> : <p className="text-sm text-muted-foreground">All questionnaire fields captured.</p>}</CardContent></Card>
                      <Card><CardHeader><CardTitle>Follow-up questions</CardTitle></CardHeader><CardContent><ul className="list-disc pl-5 text-sm">{ai.follow_up_questions.map((m: string) => <li key={m}>{m}</li>)}</ul></CardContent></Card>
                    </div>
                    <Card><CardHeader><CardTitle>Technical risks</CardTitle></CardHeader><CardContent>
                      <Table><thead><tr><Th>Risk</Th><Th>Severity</Th><Th>Mitigation</Th></tr></thead><tbody>
                        {ai.technical_risks.map((r: any) => <tr key={r.risk}><Td>{r.risk}</Td><Td><StatusBadge status={r.severity} /></Td><Td className="text-muted-foreground">{r.mitigation}</Td></tr>)}
                      </tbody></Table></CardContent></Card>
                    <Card>
                      <CardHeader className="flex-row items-center justify-between"><div><CardTitle>Proposed requirements</CardTitle><CardDescription>Import as drafts, then approve individually.</CardDescription></div>
                        {write && <Button size="sm" onClick={() => importReqs.mutate(null)} loading={importReqs.isPending}><Plus /> Import all as drafts</Button>}</CardHeader>
                      <CardContent className="space-y-2">
                        {ai.proposed_requirements.map((r: any, i: number) => (
                          <div key={i} className="flex flex-wrap items-start gap-3 rounded-lg border p-3 text-sm">
                            <div className="min-w-0 flex-1"><p className="font-medium">{r.title}</p><p className="text-xs text-muted-foreground">{r.description}</p><p className="mt-1 text-xs"><strong>Acceptance:</strong> {r.acceptance_criteria}</p></div>
                            <Badge>{label(r.category)}</Badge><StatusBadge status={r.priority} />
                            {write && <Button size="sm" variant="outline" onClick={() => importReqs.mutate([i])}>Import</Button>}
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                    <Card><CardHeader><CardTitle>Suggested acceptance criteria</CardTitle></CardHeader><CardContent><ul className="list-disc pl-5 text-sm">{ai.acceptance_criteria.map((m: string) => <li key={m}>{m}</li>)}</ul></CardContent></Card>
                  </div>
                )}
              </TabsContent>
              <TabsContent value="requirements"><Requirements sessionId={id} orgId={sess.organisation_id} reqs={reqs} write={can("discovery.write")} canApprove={can("requirements.approve")} onChange={inv} /></TabsContent>
              <TabsContent value="people"><People sessionId={id} write={can("discovery.write")} /></TabsContent>
              <TabsContent value="integrations"><IntegrationInventory orgId={sess.organisation_id} suggestions={ai.suggested_integrations ?? []} /></TabsContent>
              <TabsContent value="architecture">
                <QueryView q={archs}>{(list) => list.length === 0 ? <EmptyState title="No architecture yet" body="Approve requirements, then generate an architecture." /> : (
                  <div className="space-y-2">{list.map((a) => (
                    <Link key={a.id} href={`/app/architecture/${a.id}`} className="flex items-center justify-between rounded-lg border bg-card p-3 hover:border-primary/40"><span className="font-medium">{a.title}</span><StatusBadge status={a.status} /></Link>))}</div>)}
                </QueryView>
              </TabsContent>
            </Tabs>
          </>
        );
      }}
    </QueryView>
  );
}

function Requirements({ sessionId, orgId, reqs, write, canApprove, onChange }: any) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ title: "", description: "", category: "functional", priority: "should", acceptance_criteria: "" });
  const create = useMutation({ mutationFn: () => api("/requirements", { method: "POST", body: { ...f, session_id: sessionId, organisation_id: orgId } }),
    onSuccess: () => { setOpen(false); setF({ title: "", description: "", category: "functional", priority: "should", acceptance_criteria: "" }); onChange(); }, onError: (e) => toast.error(errorMessage(e)) });
  const decide = useMutation({ mutationFn: ({ id, decision }: { id: string; decision: string }) => api(`/requirements/${id}/decision`, { method: "POST", body: { decision } }), onSuccess: onChange, onError: (e) => toast.error(errorMessage(e)) });
  const del = useMutation({ mutationFn: (id: string) => api(`/requirements/${id}`, { method: "DELETE" }), onSuccess: onChange, onError: (e) => toast.error(errorMessage(e)) });
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between"><div><CardTitle>Requirements</CardTitle><CardDescription>Only approved requirements feed architecture and proposals.</CardDescription></div>
        {write && <Dialog open={open} onOpenChange={setOpen}><Button size="sm" onClick={() => setOpen(true)}><Plus /> Add requirement</Button>
          <DialogContent title="Add requirement">
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
              <Field label="Title" htmlFor="r-t"><Input id="r-t" required minLength={2} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
              <Field label="Description" htmlFor="r-d"><Textarea id="r-d" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Category" htmlFor="r-c"><Select id="r-c" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>{["functional", "non_functional", "security", "integration", "data"].map((c) => <option key={c} value={c}>{label(c)}</option>)}</Select></Field>
                <Field label="Priority" htmlFor="r-p"><Select id="r-p" value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>{["must", "should", "could"].map((c) => <option key={c} value={c}>{label(c)}</option>)}</Select></Field>
              </div>
              <Field label="Acceptance criteria" htmlFor="r-a"><Textarea id="r-a" value={f.acceptance_criteria} onChange={(e) => setF({ ...f, acceptance_criteria: e.target.value })} /></Field>
              <div className="flex justify-end"><Button type="submit" loading={create.isPending}>Add</Button></div>
            </form>
          </DialogContent></Dialog>}
      </CardHeader>
      <CardContent>
        <QueryView q={reqs}>{(list: any[]) => list.length === 0 ? <EmptyState title="No requirements yet" /> : (
          <Table><thead><tr><Th>Code</Th><Th>Requirement</Th><Th>Category</Th><Th>Priority</Th><Th>Source</Th><Th>Status</Th><Th /></tr></thead><tbody>
            {list.map((r) => (
              <tr key={r.id}><Td className="font-mono text-xs">{r.code}</Td><Td><p className="font-medium">{r.title}</p>{r.acceptance_criteria && <p className="text-xs text-muted-foreground">✓ {r.acceptance_criteria}</p>}</Td>
                <Td>{label(r.category)}</Td><Td><StatusBadge status={r.priority} /></Td><Td><Badge tone={r.source === "ai" ? "warning" : "neutral"}>{r.source}</Badge></Td><Td><StatusBadge status={r.status} /></Td>
                <Td className="whitespace-nowrap text-right">
                  {canApprove && r.status !== "approved" && <Button size="icon" variant="ghost" aria-label="Approve" onClick={() => decide.mutate({ id: r.id, decision: "approved" })}><Check className="text-success" /></Button>}
                  {canApprove && r.status !== "rejected" && <Button size="icon" variant="ghost" aria-label="Reject" onClick={() => decide.mutate({ id: r.id, decision: "rejected" })}><X className="text-danger" /></Button>}
                  {write && r.status !== "approved" && <Button size="sm" variant="ghost" onClick={() => del.mutate(r.id)}>Delete</Button>}
                </Td></tr>
            ))}
          </tbody></Table>)}
        </QueryView>
      </CardContent>
    </Card>
  );
}

function People({ sessionId, write }: { sessionId: string; write: boolean }) {
  const qc = useQueryClient();
  const st = useQuery({ queryKey: ["stakeholders", sessionId], queryFn: () => api<any[]>(`/discovery/sessions/${sessionId}/stakeholders`) });
  const ac = useQuery({ queryKey: ["actions", sessionId], queryFn: () => api<any[]>(`/discovery/sessions/${sessionId}/actions`) });
  const [p, setP] = useState({ name: "", role: "", influence: "medium" });
  const [a, setA] = useState({ description: "", owner: "", due_date: "" });
  const addP = useMutation({ mutationFn: () => api(`/discovery/sessions/${sessionId}/stakeholders`, { method: "POST", body: p }), onSuccess: () => { setP({ name: "", role: "", influence: "medium" }); qc.invalidateQueries({ queryKey: ["stakeholders", sessionId] }); }, onError: (e) => toast.error(errorMessage(e)) });
  const addA = useMutation({ mutationFn: () => api(`/discovery/sessions/${sessionId}/actions`, { method: "POST", body: { ...a, due_date: a.due_date || null } }), onSuccess: () => { setA({ description: "", owner: "", due_date: "" }); qc.invalidateQueries({ queryKey: ["actions", sessionId] }); }, onError: (e) => toast.error(errorMessage(e)) });
  const toggle = useMutation({ mutationFn: (x: any) => api(`/actions/${x.id}`, { method: "PATCH", body: { description: x.description, owner: x.owner, due_date: x.due_date, status: x.status === "done" ? "open" : "done" } }), onSuccess: () => qc.invalidateQueries({ queryKey: ["actions", sessionId] }) });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card><CardHeader><CardTitle>Stakeholders</CardTitle></CardHeader><CardContent className="space-y-3">
        <QueryView q={st}>{(list) => <ul className="space-y-2 text-sm">{list.map((s) => <li key={s.id} className="flex justify-between"><span><strong>{s.name}</strong> · {s.role}</span><StatusBadge status={s.influence} /></li>)}{list.length === 0 && <li className="text-muted-foreground">None yet</li>}</ul>}</QueryView>
        {write && <form className="flex flex-wrap gap-2 border-t pt-3" onSubmit={(e) => { e.preventDefault(); addP.mutate(); }}>
          <Input placeholder="Name" required minLength={2} value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} className="min-w-32 flex-1" aria-label="Stakeholder name" />
          <Input placeholder="Role" required minLength={2} value={p.role} onChange={(e) => setP({ ...p, role: e.target.value })} className="min-w-32 flex-1" aria-label="Stakeholder role" />
          <Select aria-label="Influence" value={p.influence} onChange={(e) => setP({ ...p, influence: e.target.value })} className="w-28"><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></Select>
          <Button type="submit" size="sm" loading={addP.isPending}>Add</Button></form>}
      </CardContent></Card>
      <Card><CardHeader><CardTitle>Action items</CardTitle></CardHeader><CardContent className="space-y-3">
        <QueryView q={ac}>{(list) => <ul className="space-y-2 text-sm">{list.map((x) => <li key={x.id} className="flex items-start gap-2"><input type="checkbox" checked={x.status === "done"} onChange={() => toggle.mutate(x)} disabled={!write} aria-label={`Done: ${x.description}`} className="mt-1" /><span className={x.status === "done" ? "line-through text-muted-foreground" : ""}>{x.description}<span className="block text-xs text-muted-foreground">{x.owner} · due {formatDate(x.due_date)}</span></span></li>)}{list.length === 0 && <li className="text-muted-foreground">None yet</li>}</ul>}</QueryView>
        {write && <form className="flex flex-wrap gap-2 border-t pt-3" onSubmit={(e) => { e.preventDefault(); addA.mutate(); }}>
          <Input placeholder="Action" required minLength={2} value={a.description} onChange={(e) => setA({ ...a, description: e.target.value })} className="min-w-40 flex-1" aria-label="Action description" />
          <Input placeholder="Owner" value={a.owner} onChange={(e) => setA({ ...a, owner: e.target.value })} className="w-32" aria-label="Action owner" />
          <Input type="date" value={a.due_date} onChange={(e) => setA({ ...a, due_date: e.target.value })} className="w-40" aria-label="Due date" />
          <Button type="submit" size="sm" loading={addA.isPending}>Add</Button></form>}
      </CardContent></Card>
    </div>
  );
}

function IntegrationInventory({ orgId, suggestions }: { orgId: string; suggestions: any[] }) {
  const q = useQuery({ queryKey: ["integrations", orgId], queryFn: () => api<any[]>(`/integrations?organisation_id=${orgId}`) });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card><CardHeader><CardTitle>Integration inventory</CardTitle><CardDescription>Configure credentials and test connections in Integrations.</CardDescription></CardHeader><CardContent>
        <QueryView q={q}>{(list) => list.length === 0 ? <p className="text-sm text-muted-foreground">Nothing recorded yet.</p> : <ul className="space-y-2 text-sm">{list.map((i) => <li key={i.id} className="flex justify-between"><span>{i.name} <span className="text-xs text-muted-foreground">({label(i.kind)})</span></span><StatusBadge status={i.health} /></li>)}</ul>}</QueryView>
        <Button asChild variant="link" className="mt-2"><Link href="/app/integrations">Manage integrations →</Link></Button>
      </CardContent></Card>
      <Card><CardHeader><CardTitle>AI-suggested integrations</CardTitle></CardHeader><CardContent>
        {suggestions.length === 0 ? <p className="text-sm text-muted-foreground">Run the discovery assistant to get suggestions.</p> : <ul className="space-y-2 text-sm">{suggestions.map((s) => <li key={s.kind}><strong>{s.name}</strong> · {s.purpose}</li>)}</ul>}
      </CardContent></Card>
    </div>
  );
}
