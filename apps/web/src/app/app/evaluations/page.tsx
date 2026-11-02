"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { toast } from "sonner";

import { EmptyState, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Dialog, DialogContent, Field, Input, Select, Table, Td, Textarea, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, pct } from "@/lib/utils";

const METRICS = ["correctness", "faithfulness", "context_relevance", "retrieval_precision", "retrieval_recall", "citation_quality", "tool_execution_success", "pass_rate"];

function EvalInner() {
  const params = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const { can } = useAuth();
  const apps = useQuery({ queryKey: ["apps"], queryFn: () => api<any[]>("/apps") });
  const [app, setApp] = useState(params?.get("app") ?? "");
  useEffect(() => { if (!app && apps.data?.length) setApp(apps.data[0].id); }, [apps.data, app]);
  const datasets = useQuery({ queryKey: ["datasets", app], queryFn: () => api<any[]>(`/evaluations/datasets?app_id=${app}`), enabled: !!app });
  const runs = useQuery({ queryKey: ["runs", app], queryFn: () => api<any[]>(`/evaluations/runs?app_id=${app}`), enabled: !!app,
    refetchInterval: (q) => ((q.state.data ?? []).some((r: any) => ["queued", "running"].includes(r.status)) ? 2000 : false) });
  const [ds, setDs] = useState("");
  useEffect(() => { if (datasets.data?.length && !datasets.data.find((d) => d.id === ds)) setDs(datasets.data[0].id); }, [datasets.data, ds]);
  const cases = useQuery({ queryKey: ["cases", ds], queryFn: () => api<any[]>(`/evaluations/datasets/${ds}/cases`), enabled: !!ds });
  const [selected, setSelected] = useState<string[]>([]);
  const [runOpen, setRunOpen] = useState(false);
  const [run, setRun] = useState({ label: "", provider: "", top_k: "", vector_weight: "", keyword_weight: "", min_relevance: "", llm_judge: false, prompt_version: "" });
  const [caseOpen, setCaseOpen] = useState(false);
  const [c, setC] = useState({ question: "", expected_answer: "", expected_sources: "", expected_keywords: "", must_refuse: false });
  const [dsName, setDsName] = useState("");

  const start = useMutation({
    mutationFn: () => {
      const retrieval: any = {};
      for (const k of ["top_k", "vector_weight", "keyword_weight", "min_relevance"]) if ((run as any)[k] !== "") retrieval[k] = Number((run as any)[k]);
      return api("/evaluations/runs", { method: "POST", body: { dataset_id: ds, label: run.label, provider: run.provider || null, prompt_version: run.prompt_version || null,
        retrieval: Object.keys(retrieval).length ? retrieval : null, llm_judge: run.llm_judge } });
    },
    onSuccess: () => { setRunOpen(false); toast.success("Evaluation started"); qc.invalidateQueries({ queryKey: ["runs", app] }); }, onError: (e) => toast.error(errorMessage(e)),
  });
  const addCase = useMutation({ mutationFn: () => api(`/evaluations/datasets/${ds}/cases`, { method: "POST", body: { question: c.question, expected_answer: c.expected_answer, must_refuse: c.must_refuse,
      expected_sources: c.expected_sources.split(",").map((s) => s.trim()).filter(Boolean), expected_keywords: c.expected_keywords.split(",").map((s) => s.trim()).filter(Boolean) } }),
    onSuccess: () => { setCaseOpen(false); setC({ question: "", expected_answer: "", expected_sources: "", expected_keywords: "", must_refuse: false }); qc.invalidateQueries({ queryKey: ["cases", ds] }); qc.invalidateQueries({ queryKey: ["datasets", app] }); },
    onError: (e) => toast.error(errorMessage(e)) });
  const delCase = useMutation({ mutationFn: (id: string) => api(`/evaluations/cases/${id}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["cases", ds] }) });
  const addDs = useMutation({ mutationFn: () => api("/evaluations/datasets", { method: "POST", body: { app_id: app, name: dsName } }),
    onSuccess: (d) => { setDsName(""); setDs(d.id); qc.invalidateQueries({ queryKey: ["datasets", app] }); }, onError: (e) => toast.error(errorMessage(e)) });
  const compare = useQuery({ queryKey: ["compare", selected], queryFn: () => api(`/evaluations/compare?run_ids=${selected.join(",")}`), enabled: selected.length >= 2 });

  return (
    <>
      <PageHeader title="AI evaluation" description="Deterministic metrics on every run, optional LLM-as-judge, regression alerts against the previous run."
        actions={<Select aria-label="Application" value={app} onChange={(e) => { setApp(e.target.value); router.replace(`/app/evaluations?app=${e.target.value}`); }} className="w-64">
          {(apps.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</Select>} />
      {!app ? <EmptyState icon={FlaskConical} title="No AI applications" /> : (
        <div className="space-y-6">
          <div className="grid gap-6 xl:grid-cols-[1fr_1.3fr]">
            <Card>
              <CardHeader className="flex-row flex-wrap items-center justify-between gap-2"><div><CardTitle>Test dataset</CardTitle><CardDescription>Questions with expected answers, sources and keywords; refusal cases test grounded mode.</CardDescription></div>
                <Select aria-label="Dataset" value={ds} onChange={(e) => setDs(e.target.value)} className="w-56">{(datasets.data ?? []).map((d) => <option key={d.id} value={d.id}>{d.name} ({d.case_count})</option>)}</Select></CardHeader>
              <CardContent className="space-y-3">
                <QueryView q={cases}>{(list) => (
                  <div className="max-h-96 space-y-2 overflow-y-auto">
                    {list.map((x) => (
                      <div key={x.id} className="flex items-start gap-2 rounded-lg border p-2.5 text-sm">
                        <div className="min-w-0 flex-1"><p className="font-medium">{x.question}</p>
                          <p className="text-xs text-muted-foreground">{x.must_refuse ? "Expected: refuse (insufficient evidence)" : `Expected: ${x.expected_answer} · sources ${x.expected_sources.join(", ")}`}</p></div>
                        {x.must_refuse && <Badge tone="warning">refusal</Badge>}
                        {can("evaluation.write") && <Button size="icon" variant="ghost" aria-label="Delete case" onClick={() => delCase.mutate(x.id)}><Trash2 /></Button>}
                      </div>
                    ))}
                  </div>)}
                </QueryView>
                {can("evaluation.write") && (
                  <div className="flex flex-wrap gap-2 border-t pt-3">
                    <Dialog open={caseOpen} onOpenChange={setCaseOpen}><Button size="sm" variant="outline" disabled={!ds} onClick={() => setCaseOpen(true)}><Plus /> Add case</Button>
                      <DialogContent title="Add evaluation case">
                        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); addCase.mutate(); }}>
                          <Field label="Question" htmlFor="c-q"><Textarea id="c-q" required minLength={3} value={c.question} onChange={(e) => setC({ ...c, question: e.target.value })} /></Field>
                          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={c.must_refuse} onChange={(e) => setC({ ...c, must_refuse: e.target.checked })} /> The assistant must refuse (not answerable from documents)</label>
                          {!c.must_refuse && <>
                            <Field label="Expected answer" htmlFor="c-a"><Input id="c-a" value={c.expected_answer} onChange={(e) => setC({ ...c, expected_answer: e.target.value })} /></Field>
                            <Field label="Expected source filenames (comma-separated)" htmlFor="c-s"><Input id="c-s" value={c.expected_sources} onChange={(e) => setC({ ...c, expected_sources: e.target.value })} /></Field>
                            <Field label="Expected keywords (comma-separated)" htmlFor="c-k"><Input id="c-k" value={c.expected_keywords} onChange={(e) => setC({ ...c, expected_keywords: e.target.value })} /></Field></>}
                          <div className="flex justify-end"><Button type="submit" loading={addCase.isPending}>Add</Button></div>
                        </form>
                      </DialogContent></Dialog>
                    <form className="flex flex-1 gap-2" onSubmit={(e) => { e.preventDefault(); if (dsName.trim().length >= 2) addDs.mutate(); }}>
                      <Input placeholder="New dataset name" value={dsName} onChange={(e) => setDsName(e.target.value)} aria-label="New dataset name" />
                      <Button size="sm" type="submit" variant="ghost" disabled={dsName.trim().length < 2}>Create</Button></form>
                  </div>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex-row items-center justify-between"><div><CardTitle>Runs</CardTitle><CardDescription>Select two or more runs to compare.</CardDescription></div>
                {can("evaluation.write") && <Dialog open={runOpen} onOpenChange={setRunOpen}><Button size="sm" disabled={!ds} onClick={() => setRunOpen(true)}>New run</Button>
                  <DialogContent title="Start an evaluation run" description="Leave fields blank to use the application's current configuration.">
                    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); start.mutate(); }}>
                      <Field label="Label" htmlFor="r-l"><Input id="r-l" required minLength={2} value={run.label} onChange={(e) => setRun({ ...run, label: e.target.value })} placeholder="e.g. top_k=8 experiment" /></Field>
                      <div className="grid grid-cols-2 gap-3">
                        <Field label="Provider override" htmlFor="r-p"><Select id="r-p" value={run.provider} onChange={(e) => setRun({ ...run, provider: e.target.value })}><option value="">App default</option><option value="mock">mock</option><option value="openai">openai</option><option value="anthropic">anthropic</option></Select></Field>
                        <Field label="Prompt version label" htmlFor="r-pv"><Input id="r-pv" value={run.prompt_version} onChange={(e) => setRun({ ...run, prompt_version: e.target.value })} /></Field>
                        {["top_k", "vector_weight", "keyword_weight", "min_relevance"].map((k) => <Field key={k} label={k} htmlFor={`r-${k}`}><Input id={`r-${k}`} type="number" step="0.05" value={(run as any)[k]} onChange={(e) => setRun({ ...run, [k]: e.target.value })} /></Field>)}
                      </div>
                      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={run.llm_judge} onChange={(e) => setRun({ ...run, llm_judge: e.target.checked })} /> Add LLM-as-judge scoring (requires a real provider)</label>
                      <div className="flex justify-end"><Button type="submit" loading={start.isPending}>Start</Button></div>
                    </form>
                  </DialogContent></Dialog>}
              </CardHeader>
              <CardContent>
                <QueryView q={runs}>{(list) => list.length === 0 ? <EmptyState title="No runs yet" /> : (
                  <Table><thead><tr><Th /><Th>Run</Th><Th>Status</Th><Th>Pass rate</Th><Th>Correct.</Th><Th>Faithful.</Th><Th>Regressions</Th></tr></thead><tbody>
                    {list.map((r) => (
                      <tr key={r.id} className="hover:bg-muted/40">
                        <Td><input type="checkbox" aria-label={`Compare ${r.label}`} checked={selected.includes(r.id)} onChange={(e) => setSelected(e.target.checked ? [...selected, r.id] : selected.filter((x) => x !== r.id))} /></Td>
                        <Td><Link href={`/app/evaluations/${r.id}`} className="font-medium hover:underline">{r.label}</Link><p className="text-xs text-muted-foreground">{formatDateTime(r.created_at)} · {r.config.provider}:{r.config.model} · {r.judge}</p></Td>
                        <Td><StatusBadge status={r.status} /></Td><Td className="font-semibold">{pct(r.metrics.pass_rate)}</Td><Td>{r.metrics.correctness ?? "—"}</Td><Td>{r.metrics.faithfulness ?? "—"}</Td>
                        <Td>{r.regressions.length ? <Badge tone="danger">{r.regressions.length} regression(s)</Badge> : <Badge tone="success">None</Badge>}</Td>
                      </tr>
                    ))}
                  </tbody></Table>)}
                </QueryView>
              </CardContent>
            </Card>
          </div>
          {selected.length >= 2 && (
            <Card><CardHeader><CardTitle>Comparison</CardTitle></CardHeader><CardContent>
              <QueryView q={compare}>{(cmp: any) => (
                <Table><thead><tr><Th>Metric</Th>{cmp.runs.map((r: any) => <Th key={r.id}>{r.label}</Th>)}</tr></thead><tbody>
                  {[...METRICS, "latency_p95_ms", "total_cost_usd"].map((k) => {
                    const vals = cmp.metrics[k] as (number | null)[];
                    const best = k.includes("latency") || k.includes("cost") ? Math.min(...vals.filter((v): v is number => v !== null)) : Math.max(...vals.filter((v): v is number => v !== null));
                    return <tr key={k}><Td className="text-xs">{k.replace(/_/g, " ")}</Td>{vals.map((v, i) => <Td key={i} className={v === best ? "font-semibold text-success" : ""}>{v ?? "—"}</Td>)}</tr>;
                  })}
                </tbody></Table>)}
              </QueryView>
            </CardContent></Card>
          )}
        </div>
      )}
    </>
  );
}

export default function Evaluations() {
  return <Suspense><EvalInner /></Suspense>;
}
