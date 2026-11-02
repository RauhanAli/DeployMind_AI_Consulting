"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { KeyValue, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Dialog, DialogContent, Field, Table, Td, Textarea, Th } from "@/components/ui";
import { api, errorMessage, streamEvents } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, formatDateTime } from "@/lib/utils";

const ACTIVE = ["pending", "building", "testing", "releasing"];

export function DeploymentsTable({ appId, status }: { appId?: string; status?: string }) {
  const q = useQuery({ queryKey: ["deployments", appId, status], queryFn: () => api(`/deployments?page_size=50${appId ? `&app_id=${appId}` : ""}${status ? `&status=${status}` : ""}`), refetchInterval: 5000 });
  return (
    <Card><CardHeader><CardTitle>{status === "awaiting_approval" ? "Awaiting approval" : "Release history"}</CardTitle></CardHeader><CardContent>
      <QueryView q={q}>{(d: any) => d.items.length === 0 ? <p className="text-sm text-muted-foreground">Nothing here.</p> : (
        <Table><thead><tr><Th>Version</Th>{!appId && <Th>Application</Th>}<Th>Environment</Th><Th>Status</Th><Th>Adapter</Th><Th>Triggered by</Th><Th>Started</Th></tr></thead><tbody>
          {d.items.map((x: any) => (
            <tr key={x.id} className="hover:bg-muted/40">
              <Td><Link href={`/app/deployments/${x.id}`} className="font-mono font-medium hover:underline">{x.version}</Link>
                {x.rollback_of_id && <Badge className="ml-2" tone="warning">rollback</Badge>}{x.is_demo && <Badge className="ml-2">demo record</Badge>}</Td>
              {!appId && <Td>{x.app_name}<p className="text-xs text-muted-foreground">{x.organisation_name}</p></Td>}
              <Td className="capitalize">{x.environment}</Td><Td><StatusBadge status={x.status} /></Td><Td className="text-xs">{x.adapter}</Td>
              <Td className="text-xs">{x.triggered_by_name}</Td><Td className="text-xs">{formatDateTime(x.started_at ?? x.created_at)}</Td>
            </tr>
          ))}
        </tbody></Table>)}
      </QueryView>
    </CardContent></Card>
  );
}

export function DeploymentDetail({ id }: { id: string }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const dep = useQuery({ queryKey: ["deployment", id], queryFn: () => api(`/deployments/${id}`) });
  const [logs, setLogs] = useState<any[]>([]);
  const [live, setLive] = useState(false);
  const [reject, setReject] = useState(false);
  const [reason, setReason] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const status = dep.data?.status;

  useEffect(() => {
    api<any[]>(`/deployments/${id}/logs`).then(setLogs).catch(() => undefined);
  }, [id]);
  useEffect(() => {
    if (!status || !ACTIVE.includes(status)) return;
    setLive(true);
    const seen = new Set<string>();
    setLogs([]);
    const stop = streamEvents(`/deployments/${id}/logs/stream`, (event, data) => {
      if (event === "log") {
        const key = `${data.created_at}-${data.message}`;
        if (!seen.has(key)) { seen.add(key); setLogs((l) => [...l, data]); }
      } else if (event === "status" && !ACTIVE.includes(data.status)) {
        qc.invalidateQueries({ queryKey: ["deployment", id] });
      }
    }, () => { setLive(false); qc.invalidateQueries({ queryKey: ["deployment", id] }); });
    return stop;
  }, [id, status, qc]);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [logs]);

  const inv = () => { qc.invalidateQueries({ queryKey: ["deployment", id] }); qc.invalidateQueries({ queryKey: ["deployments"] }); };
  const approve = useMutation({ mutationFn: () => api(`/deployments/${id}/approve`, { method: "POST" }), onSuccess: () => { toast.success("Approved — pipeline started"); inv(); }, onError: (e) => toast.error(errorMessage(e)) });
  const rej = useMutation({ mutationFn: () => api(`/deployments/${id}/reject`, { method: "POST", body: { reason } }), onSuccess: () => { setReject(false); inv(); }, onError: (e) => toast.error(errorMessage(e)) });

  return (
    <QueryView q={dep} rows={5}>
      {(d: any) => (
        <>
          <PageHeader title={`${d.app_name} ${d.version}`} back={{ href: "/app/deployments", label: "Deployments" }}
            description={<span className="flex flex-wrap items-center gap-2"><StatusBadge status={d.status} /><span className="capitalize">{d.environment}</span> · {d.organisation_name} · {d.adapter}</span>}
            actions={d.status === "awaiting_approval" && can("deployment.approve") && <>
              <Button variant="outline" onClick={() => setReject(true)}><X /> Reject</Button>
              <Button onClick={() => approve.mutate()} loading={approve.isPending}><Check /> Approve release</Button></>} />
          {d.is_demo && <div className="mb-4 rounded-lg border bg-muted p-3 text-sm">This is a <strong>seeded demo record</strong> describing a historical release. No container was started by this record. Use <em>Deploy</em> on an environment to run a real local Docker deployment.</div>}
          {d.status === "awaiting_approval" && <div className="mb-4 rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">Production releases require approval by someone other than the person who triggered them.</div>}
          <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
            <Card>
              <CardHeader className="flex-row items-center justify-between"><CardTitle>Pipeline logs</CardTitle>{live && <Badge tone="primary">● Live</Badge>}</CardHeader>
              <CardContent>
                <div className="max-h-[560px] overflow-y-auto rounded-lg bg-[oklch(0.18_0.01_260)] p-3 font-mono text-xs text-[oklch(0.9_0.01_260)]">
                  {logs.length === 0 && <p className="text-[oklch(0.65_0.01_260)]">No log lines yet.</p>}
                  {logs.map((l, i) => (
                    <div key={i} className={cn("flex gap-3 whitespace-pre-wrap", l.level === "error" && "text-[oklch(0.75_0.15_25)]", l.level === "warning" && "text-[oklch(0.8_0.12_80)]")}>
                      <span className="shrink-0 text-[oklch(0.6_0.01_260)]">{new Date(l.created_at).toLocaleTimeString()}</span>
                      <span className="w-24 shrink-0 text-[oklch(0.7_0.1_262)]">[{l.stage}]</span><span className="min-w-0 break-all">{l.message}</span>
                    </div>
                  ))}
                  <div ref={endRef} />
                </div>
              </CardContent>
            </Card>
            <div className="space-y-4">
              <Card><CardHeader><CardTitle>Release</CardTitle></CardHeader><CardContent>
                <KeyValue items={[["Image", <span key="i" className="font-mono text-xs">{d.image_tag ?? "—"}</span>], ["URL", d.url ? <a key="u" className="text-primary hover:underline" href={d.url} target="_blank" rel="noreferrer">{d.url}</a> : "—"],
                  ["Triggered by", d.triggered_by_name], ["Approved by", d.approved_by_name ?? "—"], ["Started", formatDateTime(d.started_at)], ["Finished", formatDateTime(d.finished_at)]]} />
                {d.error && <p className="mt-3 rounded-md bg-danger/10 p-2 text-sm text-danger">{d.error}</p>}
              </CardContent></Card>
              <Card><CardHeader><CardTitle>Configuration snapshot</CardTitle></CardHeader><CardContent><pre className="max-h-72 overflow-auto rounded-md bg-muted p-2 text-[11px]">{JSON.stringify(d.config_snapshot, null, 2)}</pre></CardContent></Card>
              {Object.keys(d.health_check ?? {}).length > 0 && <Card><CardHeader><CardTitle>Health check</CardTitle></CardHeader><CardContent><pre className="overflow-auto rounded-md bg-muted p-2 text-[11px]">{JSON.stringify(d.health_check, null, 2)}</pre></CardContent></Card>}
            </div>
          </div>
          <Dialog open={reject} onOpenChange={setReject}>
            <DialogContent title="Reject release">
              <Field label="Reason" htmlFor="rej"><Textarea id="rej" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
              <div className="mt-4 flex justify-end"><Button variant="destructive" onClick={() => rej.mutate()} disabled={reason.trim().length < 3} loading={rej.isPending}>Reject</Button></div>
            </DialogContent>
          </Dialog>
        </>
      )}
    </QueryView>
  );
}
