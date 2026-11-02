"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { toast } from "sonner";

import { AiDraftNotice, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { Mermaid } from "@/components/domain/widgets";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Dialog, DialogContent, Field, Table, Tabs, TabsContent, TabsList, TabsTrigger, Td, Textarea, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/utils";

export default function ArchitectureDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const qc = useQueryClient();
  const router = useRouter();
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["arch", id], queryFn: () => api(`/architecture/${id}`) });
  const [mermaid, setMermaid] = useState("");
  const [desc, setDesc] = useState("");
  const [deploy, setDeploy] = useState("");
  const [review, setReview] = useState(false);
  const [notes, setNotes] = useState("");
  useEffect(() => { if (q.data) { setMermaid(q.data.mermaid); setDesc(q.data.content.description); setDeploy(q.data.content.deployment_strategy); } }, [q.data]);
  const inv = () => qc.invalidateQueries({ queryKey: ["arch", id] });
  const save = useMutation({ mutationFn: () => api(`/architecture/${id}`, { method: "PUT", body: { mermaid, content: { description: desc, deployment_strategy: deploy } } }),
    onSuccess: () => { toast.success("Saved — review status reset to draft"); inv(); }, onError: (e) => toast.error(errorMessage(e)) });
  const rev = useMutation({ mutationFn: () => api(`/architecture/${id}/review`, { method: "POST", body: { notes } }),
    onSuccess: () => { setReview(false); toast.success("Marked as reviewed"); inv(); }, onError: (e) => toast.error(errorMessage(e)) });
  const proposal = useMutation({ mutationFn: () => api("/proposals/generate", { method: "POST", body: { session_id: q.data.session_id, architecture_id: id } }),
    onSuccess: (p) => router.push(`/app/proposals/${p.id}`), onError: (e) => toast.error(errorMessage(e)) });
  const write = can("architecture.write");

  return (
    <QueryView q={q} rows={6}>
      {(a: any) => {
        const c = a.content;
        const dirty = mermaid !== a.mermaid || desc !== c.description || deploy !== c.deployment_strategy;
        return (
          <>
            <PageHeader title={a.title} back={{ href: "/app/architecture", label: "Solution design" }}
              description={<span className="flex flex-wrap items-center gap-2"><StatusBadge status={a.status} />{a.generated_model} · {a.status === "reviewed" ? `reviewed ${formatDateTime(a.reviewed_at)}` : "not yet reviewed"}</span>}
              actions={<>
                {write && <Button variant="outline" onClick={() => save.mutate()} disabled={!dirty} loading={save.isPending}>Save edits</Button>}
                {can("architecture.review") && a.status !== "reviewed" && <Button variant="outline" onClick={() => setReview(true)}><ShieldCheck /> Mark reviewed</Button>}
                {can("proposal.write") && a.session_id && <Button onClick={() => proposal.mutate()} loading={proposal.isPending}><FileText /> Generate proposal</Button>}
              </>} />
            {a.status !== "reviewed" ? <div className="mb-4"><AiDraftNotice provenance={c.provenance}>This architecture is unvalidated until an engineer reviews it. Generation by an LLM is not validation.</AiDraftNotice></div> :
              <div className="mb-4 rounded-lg border border-success/30 bg-success/10 p-3 text-sm"><strong>Review notes:</strong> {a.review_notes}</div>}
            <Tabs defaultValue="diagram">
              <TabsList><TabsTrigger value="diagram">Diagram</TabsTrigger><TabsTrigger value="components">Components</TabsTrigger><TabsTrigger value="data">Data & APIs</TabsTrigger>
                <TabsTrigger value="security">Security & deployment</TabsTrigger><TabsTrigger value="risks">Risks</TabsTrigger></TabsList>
              <TabsContent value="diagram">
                <div className="grid gap-4 xl:grid-cols-2">
                  <Card><CardContent className="p-4"><Mermaid code={mermaid} /></CardContent></Card>
                  <Card><CardHeader><CardTitle>Mermaid source</CardTitle></CardHeader><CardContent>
                    <Textarea className="font-mono text-xs" rows={18} value={mermaid} disabled={!write} onChange={(e) => setMermaid(e.target.value)} aria-label="Mermaid source" />
                  </CardContent></Card>
                </div>
                <Card className="mt-4"><CardHeader><CardTitle>Architecture description</CardTitle><p className="text-sm text-muted-foreground">{c.overview}</p></CardHeader><CardContent>
                  <Textarea rows={5} value={desc} disabled={!write} onChange={(e) => setDesc(e.target.value)} aria-label="Architecture description" />
                </CardContent></Card>
              </TabsContent>
              <TabsContent value="components">
                <div className="grid gap-4 lg:grid-cols-2">
                  <Card><CardHeader><CardTitle>Components</CardTitle></CardHeader><CardContent><Table><tbody>{c.components.map((x: any) => <tr key={x.name}><Td className="font-medium">{x.name}</Td><Td className="text-xs text-muted-foreground">{x.responsibility}</Td><Td><Badge>{x.technology}</Badge></Td></tr>)}</tbody></Table></CardContent></Card>
                  <Card><CardHeader><CardTitle>Technology recommendations</CardTitle></CardHeader><CardContent className="space-y-3">{c.technology_recommendations.map((t: any) => <div key={t.area} className="text-sm"><p><strong>{t.area}:</strong> {t.choice}</p><p className="text-xs text-muted-foreground">{t.rationale}</p></div>)}</CardContent></Card>
                  <Card className="lg:col-span-2"><CardHeader><CardTitle>Integration plan</CardTitle></CardHeader><CardContent><Table><tbody>{c.integration_plan.map((x: any) => <tr key={x.system}><Td className="font-medium">{x.system}</Td><Td><Badge>{x.method}</Badge></Td><Td className="text-xs text-muted-foreground">{x.notes}</Td></tr>)}</tbody></Table></CardContent></Card>
                </div>
              </TabsContent>
              <TabsContent value="data">
                <div className="grid gap-4 lg:grid-cols-2">
                  <Card><CardHeader><CardTitle>Database design</CardTitle></CardHeader><CardContent className="space-y-3">{c.database_design.map((e: any) => <div key={e.entity} className="text-sm"><p className="font-mono font-medium">{e.entity}</p><p className="text-xs text-muted-foreground">{e.fields.join(", ")}</p>{e.notes && <p className="text-xs">{e.notes}</p>}</div>)}</CardContent></Card>
                  <Card><CardHeader><CardTitle>API contracts</CardTitle></CardHeader><CardContent><Table><thead><tr><Th>Endpoint</Th><Th>Purpose</Th></tr></thead><tbody>{c.api_contracts.map((x: any) => <tr key={x.path}><Td className="font-mono text-xs"><Badge tone="primary">{x.method}</Badge> {x.path}</Td><Td className="text-xs">{x.purpose}<br /><span className="text-muted-foreground">{x.request} → {x.response}</span></Td></tr>)}</tbody></Table></CardContent></Card>
                  <Card className="lg:col-span-2"><CardHeader><CardTitle>Data flow</CardTitle></CardHeader><CardContent><ol className="list-decimal space-y-1 pl-5 text-sm">{c.data_flow.map((d: string) => <li key={d}>{d}</li>)}</ol></CardContent></Card>
                </div>
              </TabsContent>
              <TabsContent value="security">
                <div className="grid gap-4 lg:grid-cols-2">
                  <Card><CardHeader><CardTitle>Security design</CardTitle></CardHeader><CardContent><ul className="list-disc space-y-1 pl-5 text-sm">{c.security_design.map((d: string) => <li key={d}>{d}</li>)}</ul></CardContent></Card>
                  <Card><CardHeader><CardTitle>Deployment strategy</CardTitle></CardHeader><CardContent><Textarea rows={6} value={deploy} disabled={!write} onChange={(e) => setDeploy(e.target.value)} aria-label="Deployment strategy" /></CardContent></Card>
                </div>
              </TabsContent>
              <TabsContent value="risks">
                <Card><CardContent className="p-4"><Table><thead><tr><Th>Risk</Th><Th>Likelihood</Th><Th>Impact</Th><Th>Mitigation</Th></tr></thead><tbody>
                  {c.risk_register.map((r: any) => <tr key={r.risk}><Td>{r.risk}</Td><Td><StatusBadge status={r.likelihood} /></Td><Td><StatusBadge status={r.impact} /></Td><Td className="text-muted-foreground">{r.mitigation}</Td></tr>)}
                </tbody></Table></CardContent></Card>
              </TabsContent>
            </Tabs>
            <Dialog open={review} onOpenChange={setReview}>
              <DialogContent title="Mark architecture as reviewed" description="Record what was checked and with whom. Any later edit resets the review.">
                <Field label="Review notes" htmlFor="rv"><Textarea id="rv" value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
                <div className="mt-4 flex justify-end"><Button onClick={() => rev.mutate()} disabled={notes.trim().length < 3} loading={rev.isPending}>Confirm review</Button></div>
              </DialogContent>
            </Dialog>
          </>
        );
      }}
    </QueryView>
  );
}
