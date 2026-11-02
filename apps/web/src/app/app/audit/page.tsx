"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader, QueryView } from "@/components/app/common";
import { OrgSelect } from "@/components/domain/widgets";
import { Badge, Button, Card, Input, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export default function Audit() {
  const [action, setAction] = useState("");
  const [org, setOrg] = useState("");
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["audit", action, org, page], queryFn: () => api(`/audit-logs?page=${page}&page_size=50${action ? `&action=${action}` : ""}${org ? `&organisation_id=${org}` : ""}`) });
  return (
    <>
      <PageHeader title="Audit logs" description="Append-only record of security-relevant and business actions, with actor, IP and request id." />
      <div className="mb-4 flex flex-wrap gap-2">
        <Input placeholder="Action prefix, e.g. proposal or auth.login" value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }} className="max-w-xs" aria-label="Filter by action" />
        <OrgSelect value={org} onChange={(v) => { setOrg(v); setPage(1); }} allowAll />
      </div>
      <QueryView q={q}>
        {(d: any) => (
          <>
            <Card><Table><thead><tr><Th>Time</Th><Th>Actor</Th><Th>Action</Th><Th>Resource</Th><Th>Details</Th><Th>IP / request</Th></tr></thead><tbody>
              {d.items.map((l: any) => (
                <tr key={l.id}><Td className="whitespace-nowrap text-xs">{formatDateTime(l.created_at)}</Td><Td className="text-xs">{l.actor_name ?? "anonymous"}</Td><Td><Badge tone="primary">{l.action}</Badge></Td>
                  <Td className="text-xs">{l.resource_type}<br /><span className="font-mono text-muted-foreground">{l.resource_id?.slice(0, 8)}</span></Td>
                  <Td className="max-w-xs truncate font-mono text-[11px]">{Object.keys(l.details).length ? JSON.stringify(l.details) : ""}</Td>
                  <Td className="font-mono text-[11px]">{l.ip_address}<br />{l.request_id?.slice(0, 12)}</Td></tr>
              ))}
            </tbody></Table></Card>
            <div className="mt-3 flex items-center justify-between text-sm"><span className="text-muted-foreground">{d.total} entries</span>
              <div className="flex gap-2"><Button size="sm" variant="outline" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</Button><Button size="sm" variant="outline" disabled={page * 50 >= d.total} onClick={() => setPage(page + 1)}>Next</Button></div></div>
          </>
        )}
      </QueryView>
    </>
  );
}
