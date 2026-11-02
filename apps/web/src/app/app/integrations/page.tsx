"use client";

import { label } from "@deploymind/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, PlugZap, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { OrgSelect } from "@/components/domain/widgets";
import { Badge, Button, Card, Dialog, DialogContent, Field, Input, Select, Table, Td, Textarea, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, relativeTime } from "@/lib/utils";

function Detail({ integ, onClose }: { integ: any; onClose: () => void }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const write = can("integration.write");
  const runs = useQuery({ queryKey: ["integ-runs", integ.id], queryFn: () => api<any[]>(`/integrations/${integ.id}/runs`), refetchInterval: 3000 });
  const [config, setConfig] = useState(JSON.stringify(integ.config, null, 2));
  const [retry, setRetry] = useState(JSON.stringify(integ.retry_policy));
  const [cred, setCred] = useState("");
  const [whsec, setWhsec] = useState<any>(null);
  const inv = () => { qc.invalidateQueries({ queryKey: ["integrations"] }); qc.invalidateQueries({ queryKey: ["integ-runs", integ.id] }); };
  const save = useMutation({ mutationFn: () => api(`/integrations/${integ.id}`, { method: "PATCH", body: { config: JSON.parse(config), retry_policy: JSON.parse(retry) } }),
    onSuccess: () => { toast.success("Saved"); inv(); }, onError: (e) => toast.error(e instanceof SyntaxError ? "Config must be valid JSON" : errorMessage(e)) });
  const setCredential = useMutation({ mutationFn: () => api(`/integrations/${integ.id}/credentials`, { method: "PUT", body: { value: cred } }),
    onSuccess: () => { setCred(""); toast.success("Credential stored encrypted"); inv(); }, onError: (e) => toast.error(errorMessage(e)) });
  const test = useMutation({ mutationFn: () => api(`/integrations/${integ.id}/test`, { method: "POST" }),
    onSuccess: (r) => { if (r.status === "succeeded") toast.success(r.message); else toast.error(r.error); inv(); }, onError: (e) => toast.error(errorMessage(e)) });
  const sync = useMutation({ mutationFn: () => api(`/integrations/${integ.id}/sync`, { method: "POST" }), onSuccess: () => { toast.info("Sync queued"); inv(); }, onError: (e) => toast.error(errorMessage(e)) });
  const rotate = useMutation({ mutationFn: () => api(`/integrations/${integ.id}/webhook-secret`, { method: "POST" }), onSuccess: (r) => { setWhsec(r); inv(); }, onError: (e) => toast.error(errorMessage(e)) });
  const del = useMutation({ mutationFn: () => api(`/integrations/${integ.id}`, { method: "DELETE" }), onSuccess: () => { inv(); onClose(); }, onError: (e) => toast.error(errorMessage(e)) });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={integ.name} description={`${label(integ.kind)} · ${integ.organisation_name}`} className="max-w-3xl">
        <div className="space-y-5">
          <div className="flex flex-wrap gap-2"><StatusBadge status={integ.status} /><StatusBadge status={integ.health} />{integ.has_credentials ? <Badge tone="success"><KeyRound className="size-3" /> {integ.credential_hint}</Badge> : <Badge>No credentials</Badge>}</div>
          {write && <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => test.mutate()} loading={test.isPending}><PlugZap /> Test connection</Button>
            {integ.kind !== "webhook" && <Button size="sm" variant="outline" onClick={() => sync.mutate()} loading={sync.isPending}><RefreshCw /> Sync now</Button>}
            {integ.kind === "webhook" && <Button size="sm" variant="outline" onClick={() => rotate.mutate()}>Generate signing secret</Button>}
            <Button size="sm" variant="ghost" onClick={() => confirm("Delete this integration and its credentials?") && del.mutate()}><Trash2 /> Delete</Button></div>}
          {whsec && <div className="rounded-md border border-warning/40 bg-warning/10 p-3 text-xs"><p className="font-medium">Copy this signing secret now — it will not be shown again.</p><code className="break-all">{whsec.secret}</code><p className="mt-1">POST {whsec.endpoint} with header {whsec.signature_header}: {whsec.algorithm}</p></div>}
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Configuration (JSON, non-secret)" htmlFor="ic"><Textarea id="ic" rows={7} className="font-mono text-xs" disabled={!write} value={config} onChange={(e) => setConfig(e.target.value)} /></Field>
            <div className="space-y-3">
              <Field label="Retry policy (JSON)" htmlFor="ir"><Input id="ir" className="font-mono text-xs" disabled={!write} value={retry} onChange={(e) => setRetry(e.target.value)} /></Field>
              {write && <Button size="sm" variant="outline" onClick={() => save.mutate()} loading={save.isPending}>Save configuration</Button>}
              {write && integ.kind !== "webhook" && (
                <form className="space-y-2 border-t pt-3" onSubmit={(e) => { e.preventDefault(); setCredential.mutate(); }}>
                  <Field label={integ.kind === "postgres" ? "Database password" : "API token"} htmlFor="icred" hint="Write-only. Encrypted at rest; never returned by the API.">
                    <Input id="icred" type="password" autoComplete="off" value={cred} onChange={(e) => setCred(e.target.value)} /></Field>
                  <Button size="sm" type="submit" disabled={cred.length < 4} loading={setCredential.isPending}>Store credential</Button>
                </form>
              )}
            </div>
          </div>
          <div><p className="mb-2 text-sm font-medium">Sync history & error log</p>
            <QueryView q={runs}>{(list) => list.length === 0 ? <p className="text-sm text-muted-foreground">No runs yet.</p> : (
              <Table><thead><tr><Th>When</Th><Th>Kind</Th><Th>Status</Th><Th>Attempts</Th><Th>Records</Th><Th>Message</Th></tr></thead><tbody>
                {list.map((r) => <tr key={r.id}><Td className="text-xs">{formatDateTime(r.created_at)}</Td><Td>{r.kind}</Td><Td><StatusBadge status={r.status} /></Td><Td>{r.attempts}</Td><Td>{r.records_processed}</Td>
                  <Td className="max-w-xs text-xs">{r.message}{r.error && <span className="block text-danger">{r.error}</span>}</Td></tr>)}</tbody></Table>)}
            </QueryView></div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function Integrations() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const [org, setOrg] = useState("");
  const [open, setOpen] = useState<any | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [f, setF] = useState({ organisation_id: "", name: "", kind: "rest_api", description: "", base_url: "" });
  const q = useQuery({ queryKey: ["integrations", org], queryFn: () => api<any[]>(`/integrations${org ? `?organisation_id=${org}` : ""}`) });
  const kinds = useQuery({ queryKey: ["integration-kinds"], queryFn: () => api("/integrations/kinds") });
  const create = useMutation({ mutationFn: () => api("/integrations", { method: "POST", body: { organisation_id: f.organisation_id, name: f.name, kind: f.kind, description: f.description,
      config: f.base_url ? { base_url: f.base_url, health_path: "/health" } : {}, retry_policy: { max_attempts: 3, backoff_seconds: 2 } } }),
    onSuccess: (i) => { setNewOpen(false); qc.invalidateQueries({ queryKey: ["integrations"] }); setOpen(i); }, onError: (e) => toast.error(errorMessage(e)) });
  const current = open ? (q.data ?? []).find((i) => i.id === open.id) ?? open : null;
  return (
    <>
      <PageHeader title="Integrations" description="REST APIs, webhooks, PostgreSQL, CRM, ticketing and document stores — with encrypted credentials, retries and health."
        actions={<><OrgSelect value={org} onChange={setOrg} allowAll />{can("integration.write") && (
          <Dialog open={newOpen} onOpenChange={setNewOpen}><Button onClick={() => setNewOpen(true)}>New integration</Button>
            <DialogContent title="New integration" description="Demo connectors can point at the built-in mock services, e.g. http://localhost:8000/api/v1/mock-services/crm (token must start with dm_mock_).">
              <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
                <Field label="Organisation" htmlFor="n-org"><OrgSelect id="n-org" value={f.organisation_id} onChange={(v) => setF({ ...f, organisation_id: v })} /></Field>
                <Field label="Name" htmlFor="n-name"><Input id="n-name" required minLength={2} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
                <Field label="Type" htmlFor="n-kind"><Select id="n-kind" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>{Object.entries(kinds.data ?? {}).map(([k, v]: any) => <option key={k} value={k}>{v.label}</option>)}</Select></Field>
                {!["postgres", "webhook"].includes(f.kind) && <Field label="Base URL" htmlFor="n-url"><Input id="n-url" value={f.base_url} onChange={(e) => setF({ ...f, base_url: e.target.value })} placeholder="https://api.example.com" /></Field>}
                <Field label="Description" htmlFor="n-desc"><Textarea id="n-desc" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
                <div className="flex justify-end"><Button type="submit" disabled={!f.organisation_id || f.name.length < 2} loading={create.isPending}>Create</Button></div>
              </form>
            </DialogContent></Dialog>)}</>} />
      <QueryView q={q}>
        {(list) => list.length === 0 ? <EmptyState icon={PlugZap} title="No integrations" /> : (
          <Card><Table><thead><tr><Th>Integration</Th><Th>Organisation</Th><Th>Type</Th><Th>Status</Th><Th>Health</Th><Th>Credentials</Th><Th>Last test / sync</Th></tr></thead><tbody>
            {list.map((i) => (
              <tr key={i.id} className="cursor-pointer hover:bg-muted/40" onClick={() => setOpen(i)}>
                <Td className="font-medium">{i.name}<p className="text-xs text-muted-foreground">{i.description}</p></Td><Td>{i.organisation_name}</Td><Td>{label(i.kind)}</Td>
                <Td><StatusBadge status={i.status} /></Td><Td><StatusBadge status={i.health} /></Td><Td>{i.has_credentials ? <Badge tone="success">{i.credential_hint ?? "set"}</Badge> : <Badge>none</Badge>}</Td>
                <Td className="text-xs">{relativeTime(i.last_tested_at)} / {relativeTime(i.last_synced_at)}</Td>
              </tr>
            ))}
          </tbody></Table></Card>
        )}
      </QueryView>
      {current && <Detail integ={current} onClose={() => setOpen(null)} />}
    </>
  );
}
