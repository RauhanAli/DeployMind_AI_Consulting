"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HeartPulse, Rocket, RotateCcw, Square } from "lucide-react";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import { toast } from "sonner";

import { KeyValue, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { DeploymentsTable } from "@/components/domain/deploy";
import { ChatPanel, DocumentsPanel } from "@/components/domain/knowledge";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Field, Input, Select, Table, Tabs, TabsContent, TabsList, TabsTrigger, Td, Textarea } from "@/components/ui";
import { api, errorMessage, newIdempotencyKey } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { relativeTime } from "@/lib/utils";

const MODELS: Record<string, string[]> = { mock: ["mock-deterministic-1"], openai: ["gpt-4o-mini", "gpt-4o"], anthropic: ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"] };

function Config({ app, write }: { app: any; write: boolean }) {
  const qc = useQueryClient();
  const providers = useQuery({ queryKey: ["providers"], queryFn: () => api("/ai/providers") });
  const [f, setF] = useState<any>(app);
  useEffect(() => {
    setF(app);
  }, [app]);
  const save = useMutation({
    mutationFn: () => api(`/apps/${app.id}`, { method: "PATCH", body: { name: f.name, description: f.description, provider: f.provider, model: f.model, temperature: Number(f.temperature),
      max_output_tokens: Number(f.max_output_tokens), system_prompt: f.system_prompt, prompt_version: f.prompt_version, grounded_mode: f.grounded_mode, status: f.status,
      retrieval_config: Object.fromEntries(Object.entries(f.retrieval_config).map(([k, v]) => [k, Number(v)])) } }),
    onSuccess: () => { toast.success("Configuration saved"); qc.invalidateQueries({ queryKey: ["app", app.id] }); }, onError: (e) => toast.error(errorMessage(e)),
  });
  const rc = f.retrieval_config;
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Card><CardHeader><CardTitle>Model</CardTitle><CardDescription>Switch providers without code changes. Unconfigured providers are rejected by the API.</CardDescription></CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <Field label="Provider" htmlFor="c-prov"><Select id="c-prov" disabled={!write} value={f.provider} onChange={(e) => setF({ ...f, provider: e.target.value, model: MODELS[e.target.value][0] })}>
            {(providers.data?.providers ?? [{ provider: "mock", configured: true }]).map((p: any) => <option key={p.provider} value={p.provider} disabled={!p.configured}>{p.provider}{p.configured ? "" : " (no API key)"}</option>)}</Select></Field>
          <Field label="Model" htmlFor="c-model"><Select id="c-model" disabled={!write} value={f.model} onChange={(e) => setF({ ...f, model: e.target.value })}>{(MODELS[f.provider] ?? [f.model]).map((m) => <option key={m}>{m}</option>)}</Select></Field>
          <Field label="Temperature" htmlFor="c-temp"><Input id="c-temp" type="number" step="0.05" min={0} max={1.5} disabled={!write} value={f.temperature} onChange={(e) => setF({ ...f, temperature: e.target.value })} /></Field>
          <Field label="Max output tokens" htmlFor="c-max"><Input id="c-max" type="number" min={64} max={4000} disabled={!write} value={f.max_output_tokens} onChange={(e) => setF({ ...f, max_output_tokens: e.target.value })} /></Field>
          <Field label="Prompt version" htmlFor="c-pv"><Input id="c-pv" disabled={!write} value={f.prompt_version} onChange={(e) => setF({ ...f, prompt_version: e.target.value })} /></Field>
          <Field label="Status" htmlFor="c-status"><Select id="c-status" disabled={!write} value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}><option value="draft">Draft (internal only)</option><option value="active">Active (visible to customer)</option><option value="archived">Archived</option></Select></Field>
          <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" disabled={!write} checked={f.grounded_mode} onChange={(e) => setF({ ...f, grounded_mode: e.target.checked })} /> Grounded mode — answer only from authorised retrieved context, refuse otherwise</label>
          <div className="sm:col-span-2"><Field label="System prompt" htmlFor="c-sys"><Textarea id="c-sys" rows={6} className="font-mono text-xs" disabled={!write} value={f.system_prompt} onChange={(e) => setF({ ...f, system_prompt: e.target.value })} /></Field></div>
        </CardContent></Card>
      <Card><CardHeader><CardTitle>Retrieval</CardTitle><CardDescription>Hybrid pgvector cosine + Postgres full-text, fused with weighted reciprocal-rank fusion.</CardDescription></CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          {[["top_k", "Top K chunks", 1], ["vector_weight", "Vector weight", 0.05], ["keyword_weight", "Keyword weight", 0.05], ["min_relevance", "Minimum relevance (refusal threshold)", 0.05], ["min_term_coverage", "Minimum question-term coverage", 0.05], ["chunk_size", "Chunk size (chars)", 50], ["chunk_overlap", "Chunk overlap (chars)", 10]].map(([k, l, step]) => (
            <Field key={k as string} label={l as string} htmlFor={`rc-${k}`}><Input id={`rc-${k}`} type="number" step={step as number} disabled={!write} value={rc[k as string] ?? ""} onChange={(e) => setF({ ...f, retrieval_config: { ...rc, [k as string]: e.target.value } })} /></Field>
          ))}
          <p className="text-xs text-muted-foreground sm:col-span-2">Chunking changes apply to newly ingested or reprocessed documents. Compare configurations safely with an evaluation run first.</p>
        </CardContent></Card>
      {write && <div className="xl:col-span-2"><Button onClick={() => save.mutate()} loading={save.isPending}>Save configuration</Button></div>}
    </div>
  );
}

function Environments({ appId }: { appId: string }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const envs = useQuery({ queryKey: ["envs", appId], queryFn: () => api<any[]>(`/apps/${appId}/environments`), refetchInterval: 5000 });
  const adapters = useQuery({ queryKey: ["adapters"], queryFn: () => api<any[]>("/deployments/adapters") });
  const inv = () => { qc.invalidateQueries({ queryKey: ["envs", appId] }); qc.invalidateQueries({ queryKey: ["deployments"] }); };
  const act = useMutation({ mutationFn: ({ id, action }: { id: string; action: string }) => api(`/environments/${id}/${action}`, { method: "POST", idempotencyKey: action === "deploy" ? newIdempotencyKey() : undefined }),
    onSuccess: (r, v) => { inv(); if (v.action === "deploy" || v.action === "rollback") toast.success(r.status === "awaiting_approval" ? `${r.version} awaiting production approval` : `${r.version} queued`); else if (v.action === "health-check") toast.info(`Health: ${r.status}`); },
    onError: (e) => toast.error(errorMessage(e)) });
  const [secret, setSecret] = useState<Record<string, { name: string; value: string }>>({});
  const [vars, setVars] = useState<Record<string, string>>({});
  const saveSecret = useMutation({ mutationFn: ({ id }: { id: string }) => api(`/environments/${id}/secrets`, { method: "PUT", body: secret[id] }),
    onSuccess: (_r, v) => { setSecret({ ...secret, [v.id]: { name: "", value: "" } }); inv(); toast.success("Secret stored encrypted"); }, onError: (e) => toast.error(errorMessage(e)) });
  const saveVars = useMutation({ mutationFn: ({ id }: { id: string }) => {
      const parsed = Object.fromEntries(vars[id].split("\n").map((l) => l.trim()).filter(Boolean).map((l) => { const i = l.indexOf("="); return [l.slice(0, i).trim(), l.slice(i + 1).trim()]; }));
      return api(`/environments/${id}`, { method: "PATCH", body: { variables: parsed } });
    }, onSuccess: () => { inv(); toast.success("Variables saved"); }, onError: (e) => toast.error(errorMessage(e)) });
  const local = adapters.data?.find((a) => a.adapter === "local_docker");
  return (
    <div className="space-y-4">
      {local && !local.available && <div className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">Local Docker adapter unavailable: {local.reason}. Deployments will fail honestly until Docker is reachable by the worker.</div>}
      <QueryView q={envs}>
        {(list) => (
          <div className="grid gap-4 xl:grid-cols-3">
            {list.map((e) => (
              <Card key={e.id}>
                <CardHeader className="flex-row items-start justify-between">
                  <div><CardTitle className="capitalize">{e.name}</CardTitle><CardDescription>{e.adapter}{e.requires_approval && " · approval required"}</CardDescription></div>
                  <StatusBadge status={e.health_status} />
                </CardHeader>
                <CardContent className="space-y-4">
                  <KeyValue items={[["Current version", e.current_version ?? "—"], ["URL", e.url ? <a key="u" href={e.url} target="_blank" rel="noreferrer" className="text-primary hover:underline">{e.url}</a> : "—"],
                    ["Resources", `${e.resources.cpu} vCPU · ${e.resources.memory_mb} MB · ${e.resources.replicas}×`], ["Last health check", relativeTime(e.last_health_check_at)]]} />
                  {can("deployment.write") && (
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" onClick={() => act.mutate({ id: e.id, action: "deploy" })} loading={act.isPending && act.variables?.id === e.id && act.variables.action === "deploy"}><Rocket /> Deploy</Button>
                      <Button size="sm" variant="outline" onClick={() => act.mutate({ id: e.id, action: "rollback" })}><RotateCcw /> Rollback</Button>
                      <Button size="sm" variant="outline" onClick={() => act.mutate({ id: e.id, action: "health-check" })}><HeartPulse /> Check</Button>
                      {e.current_deployment_id && <Button size="sm" variant="ghost" onClick={() => confirm(`Stop ${e.name}?`) && act.mutate({ id: e.id, action: "stop" })}><Square /> Stop</Button>}
                    </div>
                  )}
                  <div className="space-y-2 border-t pt-3">
                    <p className="text-xs font-medium">Environment variables</p>
                    <Textarea rows={3} className="font-mono text-xs" disabled={!can("deployment.write")} aria-label={`${e.name} variables`}
                      value={vars[e.id] ?? Object.entries(e.variables).map(([k, v]) => `${k}=${v}`).join("\n")} onChange={(ev) => setVars({ ...vars, [e.id]: ev.target.value })} />
                    {can("deployment.write") && vars[e.id] !== undefined && <Button size="sm" variant="outline" onClick={() => saveVars.mutate({ id: e.id })}>Save variables</Button>}
                  </div>
                  <div className="space-y-2 border-t pt-3">
                    <p className="text-xs font-medium">Secrets (write-only, encrypted)</p>
                    <div className="flex flex-wrap gap-1">{e.secret_names.map((s: string) => <Badge key={s}>{s}</Badge>)}{e.secret_names.length === 0 && <span className="text-xs text-muted-foreground">None</span>}</div>
                    {can("deployment.write") && (
                      <form className="flex flex-wrap gap-2" onSubmit={(ev) => { ev.preventDefault(); saveSecret.mutate({ id: e.id }); }}>
                        <Input placeholder="NAME" className="w-32 font-mono text-xs" value={secret[e.id]?.name ?? ""} onChange={(ev) => setSecret({ ...secret, [e.id]: { ...(secret[e.id] ?? { value: "" }), name: ev.target.value.toUpperCase() } })} aria-label="Secret name" />
                        <Input placeholder="value" type="password" className="min-w-24 flex-1" value={secret[e.id]?.value ?? ""} onChange={(ev) => setSecret({ ...secret, [e.id]: { ...(secret[e.id] ?? { name: "" }), value: ev.target.value } })} aria-label="Secret value" autoComplete="off" />
                        <Button size="sm" type="submit" variant="outline" disabled={!secret[e.id]?.name || !secret[e.id]?.value}>Set</Button>
                      </form>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </QueryView>
      <DeploymentsTable appId={appId} />
    </div>
  );
}

function Feedback({ appId }: { appId: string }) {
  const q = useQuery({ queryKey: ["feedback", appId], queryFn: () => api(`/apps/${appId}/feedback`) });
  return (
    <QueryView q={q}>{(f: any) => (
      <Card><CardHeader><CardTitle>User feedback</CardTitle><CardDescription>👍 {f.positive} · 👎 {f.negative}</CardDescription></CardHeader><CardContent>
        {f.items.length === 0 ? <p className="text-sm text-muted-foreground">No feedback yet.</p> : (
          <Table><tbody>{f.items.map((i: any) => <tr key={i.message_id}><Td>{i.rating > 0 ? "👍" : "👎"}</Td><Td className="text-sm">{i.answer}{i.comment && <p className="text-xs text-muted-foreground">“{i.comment}”</p>}</Td><Td className="text-xs">{i.user}<br />{relativeTime(i.created_at)}</Td></tr>)}</tbody></Table>)}
      </CardContent></Card>)}
    </QueryView>
  );
}

export default function AppDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["app", id], queryFn: () => api(`/apps/${id}`) });
  return (
    <QueryView q={q} rows={6}>
      {(app: any) => (
        <>
          <PageHeader title={app.name} back={{ href: "/app/apps", label: "AI applications" }}
            description={<span className="flex flex-wrap items-center gap-2"><StatusBadge status={app.status} />{app.organisation_name} · {app.provider}:{app.model} · prompt {app.prompt_version}</span>}
            actions={<Button variant="outline" asChild><Link href={`/app/evaluations?app=${id}`}>Evaluations</Link></Button>} />
          <Tabs defaultValue="playground">
            <TabsList><TabsTrigger value="playground">Playground</TabsTrigger><TabsTrigger value="documents">Documents</TabsTrigger><TabsTrigger value="config">Configuration</TabsTrigger>
              <TabsTrigger value="environments">Environments & deploy</TabsTrigger><TabsTrigger value="feedback">Feedback</TabsTrigger></TabsList>
            <TabsContent value="playground"><ChatPanel appId={id} showDiagnostics /></TabsContent>
            <TabsContent value="documents"><DocumentsPanel appId={id} canWrite={can("document.write")} internal /></TabsContent>
            <TabsContent value="config"><Config app={app} write={can("app.write")} /></TabsContent>
            <TabsContent value="environments"><Environments appId={id} /></TabsContent>
            <TabsContent value="feedback"><Feedback appId={id} /></TabsContent>
          </Tabs>
        </>
      )}
    </QueryView>
  );
}
