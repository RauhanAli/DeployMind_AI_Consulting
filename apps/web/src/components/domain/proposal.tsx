"use client";

import { PROPOSAL_FLOW, label } from "@deploymind/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, Pencil, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { AiDraftNotice, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Dialog, DialogContent, Field, Input, Table, Td, Textarea, Th } from "@/components/ui";
import { api, downloadFile, errorMessage, newIdempotencyKey } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime, money } from "@/lib/utils";

const TEXT_SECTIONS: [string, string][] = [["executive_summary", "Executive summary"], ["business_problem", "Business problem"],
  ["proposed_solution", "Proposed solution"], ["technical_architecture", "Technical architecture"], ["support_agreement", "Support agreement"]];
const LIST_SECTIONS: [string, string][] = [["deliverables", "Deliverables"], ["risks_and_assumptions", "Risks and assumptions"], ["acceptance_criteria", "Acceptance criteria"]];

export function ProposalDetail({ id, area }: { id: string; area: "portal" | "internal" }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["proposal", id], queryFn: () => api(`/proposals/${id}`) });
  const [editing, setEditing] = useState(false);
  const [decision, setDecision] = useState<"accepted" | "rejected" | null>(null);
  const [comment, setComment] = useState("");
  const refresh = () => { qc.invalidateQueries({ queryKey: ["proposal", id] }); qc.invalidateQueries({ queryKey: ["proposals"] }); };

  const transition = useMutation({ mutationFn: (status: string) => api(`/proposals/${id}/transition`, { method: "POST", body: { status } }),
    onSuccess: (_d, s) => { toast.success(`Proposal ${label(s).toLowerCase()}`); refresh(); }, onError: (e) => toast.error(errorMessage(e)) });
  const decide = useMutation({
    mutationFn: () => api(`/proposals/${id}/decision`, { method: "POST", body: { decision, comment: comment || null }, idempotencyKey: newIdempotencyKey() }),
    onSuccess: () => { toast.success(decision === "accepted" ? "Proposal accepted — your project has been created" : "Proposal rejected"); setDecision(null); refresh(); qc.invalidateQueries(); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <QueryView q={q} rows={8}>
      {(p: any) => {
        const c = p.content;
        const next = PROPOSAL_FLOW[p.status] ?? [];
        return (
          <>
            <PageHeader title={p.title} back={{ href: area === "portal" ? "/portal/proposals" : "/app/proposals", label: "Proposals" }}
              description={<span className="flex flex-wrap items-center gap-2"><StatusBadge status={p.status} /> Version {p.current_version} · {p.organisation_name} · updated {formatDate(p.updated_at)}</span>}
              actions={<>
                <Button variant="outline" onClick={() => downloadFile(`/proposals/${id}/pdf`, `proposal-v${p.current_version}.pdf`).catch((e) => toast.error(errorMessage(e)))}><Download /> PDF</Button>
                {area === "internal" && can("proposal.write") && ["draft", "rejected"].includes(p.status) && <Button variant="outline" onClick={() => setEditing(true)}><Pencil /> Edit</Button>}
                {area === "internal" && next.map((s) => (
                  <Button key={s} variant={s === "draft" ? "ghost" : "default"} onClick={() => transition.mutate(s)} loading={transition.isPending && transition.variables === s}
                    disabled={(s === "approved" || s === "sent") && !can("proposal.approve")} title={(s === "approved" || s === "sent") && !can("proposal.approve") ? "Requires proposal.approve" : undefined}>
                    {s === "in_review" ? "Submit for review" : s === "approved" ? "Approve" : s === "sent" ? "Send to customer" : "Back to draft"}
                  </Button>
                ))}
                {area === "portal" && p.status === "sent" && can("proposal.decide") && <>
                  <Button variant="outline" onClick={() => setDecision("rejected")}><X /> Reject</Button>
                  <Button onClick={() => setDecision("accepted")}><Check /> Accept proposal</Button>
                </>}
              </>} />

            {area === "internal" && ["draft", "in_review"].includes(p.status) && <div className="mb-4"><AiDraftNotice provenance={c.provenance}>AI-generated proposals remain drafts until approved by an authorised reviewer (different from the author).</AiDraftNotice></div>}
            {p.project_id && (
              <div className="mb-4 rounded-lg border border-success/30 bg-success/10 p-3 text-sm">
                Accepted {formatDateTime(p.decided_at)}. <Link className="font-medium text-primary hover:underline" href={`/${area === "portal" ? "portal" : "app"}/projects/${p.project_id}`}>Open project →</Link>
              </div>
            )}

            <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
              <div className="space-y-4">
                {TEXT_SECTIONS.map(([k, t]) => c[k] && (
                  <Card key={k}><CardHeader><CardTitle>{t}</CardTitle></CardHeader><CardContent><p className="whitespace-pre-wrap text-sm leading-relaxed">{c[k]}</p></CardContent></Card>
                ))}
                {LIST_SECTIONS.map(([k, t]) => c[k]?.length > 0 && (
                  <Card key={k}><CardHeader><CardTitle>{t}</CardTitle></CardHeader><CardContent><ul className="list-disc space-y-1 pl-5 text-sm">{c[k].map((x: string) => <li key={x}>{x}</li>)}</ul></CardContent></Card>
                ))}
              </div>
              <div className="space-y-4">
                <Card>
                  <CardHeader><CardTitle>Investment</CardTitle></CardHeader>
                  <CardContent className="space-y-3">
                    <p className="text-3xl font-semibold">{money(c.total, c.currency)}</p>
                    <Badge tone="warning">Estimate</Badge>
                    <Table><tbody>{(c.costs ?? []).map((x: any) => <tr key={x.item}><Td className="text-xs">{x.item}</Td><Td className="text-right font-mono text-xs">{money(x.amount, c.currency)}</Td></tr>)}</tbody></Table>
                    <p className="text-xs text-muted-foreground">{c.estimate_label}</p>
                    {area === "internal" && c.estimate_basis && <ul className="list-disc pl-4 text-xs text-muted-foreground">{c.estimate_basis.map((b: string) => <li key={b}>{b}</li>)}</ul>}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader><CardTitle>Timeline · {c.timeline_weeks} weeks</CardTitle></CardHeader>
                  <CardContent className="space-y-2">
                    {(c.milestones ?? []).map((m: any) => (
                      <div key={m.title} className="text-sm">
                        <div className="flex justify-between"><span>{m.title}</span><span className="text-xs text-muted-foreground">wk {m.start_week}–{m.start_week + m.weeks - 1}</span></div>
                        <div className="mt-1 h-1.5 rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ marginLeft: `${((m.start_week - 1) / c.timeline_weeks) * 100}%`, width: `${(m.weeks / c.timeline_weeks) * 100}%` }} /></div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader><CardTitle>Team</CardTitle></CardHeader>
                  <CardContent><ul className="space-y-1 text-sm">{(c.team ?? []).map((t: any) => <li key={t.role} className="flex justify-between"><span>{t.role}</span><span className="text-muted-foreground">{Math.round(t.allocation * 100)}%</span></li>)}</ul></CardContent>
                </Card>
                {area === "internal" && p.versions?.length > 0 && (
                  <Card>
                    <CardHeader><CardTitle>Version history</CardTitle></CardHeader>
                    <CardContent><Table><thead><tr><Th>v</Th><Th>Source</Th><Th>Note</Th></tr></thead><tbody>
                      {p.versions.map((v: any) => <tr key={v.version}><Td>{v.version}</Td><Td><Badge tone={v.source === "ai" ? "warning" : "neutral"}>{v.source}</Badge></Td><Td className="text-xs">{v.change_note}<br /><span className="text-muted-foreground">{formatDateTime(v.created_at)}</span></Td></tr>)}
                    </tbody></Table></CardContent>
                  </Card>
                )}
              </div>
            </div>

            {editing && <EditProposal p={p} onClose={() => setEditing(false)} onSaved={refresh} />}
            <Dialog open={!!decision} onOpenChange={(o) => !o && setDecision(null)}>
              <DialogContent title={decision === "accepted" ? "Accept this proposal?" : "Reject this proposal?"}
                description={decision === "accepted" ? "Accepting starts the project. DeployMind will be notified immediately." : "Let us know why so we can revise it."}>
                <Field label="Comment (optional)" htmlFor="decision-comment"><Textarea id="decision-comment" value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
                <div className="mt-4 flex justify-end gap-2">
                  <Button variant="outline" onClick={() => setDecision(null)}>Cancel</Button>
                  <Button variant={decision === "rejected" ? "destructive" : "default"} onClick={() => decide.mutate()} loading={decide.isPending}>
                    {decision === "accepted" ? "Accept" : "Reject"}
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </>
        );
      }}
    </QueryView>
  );
}

function EditProposal({ p, onClose, onSaved }: { p: any; onClose: () => void; onSaved: () => void }) {
  const [content, setContent] = useState<any>(() => JSON.parse(JSON.stringify(p.content)));
  const [note, setNote] = useState("");
  const save = useMutation({
    mutationFn: () => {
      const body: any = {};
      for (const [k] of [...TEXT_SECTIONS, ...LIST_SECTIONS]) body[k] = content[k];
      body.costs = content.costs.map((c: any) => ({ item: c.item, amount: Number(c.amount) }));
      return api(`/proposals/${p.id}`, { method: "PUT", body: { content: body, change_note: note || "Edited" } });
    },
    onSuccess: () => { toast.success("Saved as a new version"); onSaved(); onClose(); }, onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Edit proposal" description="Saving creates a new version. Totals are recalculated from cost lines." className="max-w-3xl">
        <div className="space-y-4">
          {TEXT_SECTIONS.map(([k, t]) => (
            <Field key={k} label={t} htmlFor={k}><Textarea id={k} rows={4} value={content[k] ?? ""} onChange={(e) => setContent({ ...content, [k]: e.target.value })} /></Field>
          ))}
          {LIST_SECTIONS.map(([k, t]) => (
            <Field key={k} label={`${t} (one per line)`} htmlFor={k}>
              <Textarea id={k} rows={4} value={(content[k] ?? []).join("\n")} onChange={(e) => setContent({ ...content, [k]: e.target.value.split("\n").filter((x: string) => x.trim()) })} />
            </Field>
          ))}
          <div className="space-y-2">
            <p className="text-sm font-medium">Cost lines</p>
            {content.costs.map((c: any, i: number) => (
              <div key={i} className="flex gap-2">
                <Input aria-label="Cost item" value={c.item} onChange={(e) => { const costs = [...content.costs]; costs[i] = { ...c, item: e.target.value }; setContent({ ...content, costs }); }} />
                <Input aria-label="Amount" type="number" min={0} className="w-36" value={c.amount} onChange={(e) => { const costs = [...content.costs]; costs[i] = { ...c, amount: e.target.value }; setContent({ ...content, costs }); }} />
              </div>
            ))}
          </div>
          <Field label="Change note" htmlFor="note"><Input id="note" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <div className="flex justify-end gap-2"><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={() => save.mutate()} loading={save.isPending}>Save version</Button></div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
