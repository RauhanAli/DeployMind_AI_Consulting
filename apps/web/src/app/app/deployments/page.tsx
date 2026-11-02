"use client";

import { useQuery } from "@tanstack/react-query";

import { PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { DeploymentsTable } from "@/components/domain/deploy";
import { Badge, Card, CardContent, CardHeader, CardTitle, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { relativeTime } from "@/lib/utils";

export default function Deployments() {
  const envs = useQuery({ queryKey: ["environments"], queryFn: () => api<any[]>("/environments"), refetchInterval: 10000 });
  const adapters = useQuery({ queryKey: ["adapters"], queryFn: () => api<any[]>("/deployments/adapters") });
  return (
    <>
      <PageHeader title="Deployments" description="Build → test → containerise → release → health check, with approval gates and rollback." />
      <div className="space-y-6">
        <DeploymentsTable status="awaiting_approval" />
        <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
          <Card><CardHeader><CardTitle>Environments</CardTitle></CardHeader><CardContent>
            <QueryView q={envs}>{(list) => (
              <Table><thead><tr><Th>Application</Th><Th>Environment</Th><Th>Version</Th><Th>Health</Th><Th>Checked</Th></tr></thead><tbody>
                {list.map((e) => <tr key={e.id}><Td><a className="font-medium hover:underline" href={`/app/apps/${e.app_id}`}>{e.app_name}</a></Td><Td className="capitalize">{e.name}{e.requires_approval && <Badge className="ml-2" tone="warning">gated</Badge>}</Td>
                  <Td className="font-mono text-xs">{e.current_version ?? "—"}</Td><Td><StatusBadge status={e.health_status} /></Td><Td className="text-xs">{relativeTime(e.last_health_check_at)}</Td></tr>)}
              </tbody></Table>)}
            </QueryView>
          </CardContent></Card>
          <Card><CardHeader><CardTitle>Deployment adapters</CardTitle></CardHeader><CardContent className="space-y-3">
            <QueryView q={adapters}>{(list) => list.map((a) => (
              <div key={a.adapter} className="rounded-lg border p-3 text-sm">
                <div className="flex items-center justify-between"><span className="font-mono">{a.adapter}</span>{a.available ? <Badge tone="success">Available</Badge> : <Badge tone="neutral">Not configured</Badge>}</div>
                <p className="mt-1 text-xs text-muted-foreground">{a.label}</p>{a.reason && <p className="text-xs text-muted-foreground">{a.reason}</p>}
                {a.checked_by && <p className="text-[11px] text-muted-foreground">checked by {a.checked_by}</p>}
              </div>))}
            </QueryView>
          </CardContent></Card>
        </div>
        <DeploymentsTable />
      </div>
    </>
  );
}
