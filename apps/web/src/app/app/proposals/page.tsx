"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { EmptyState, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { Card, Select, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { money, relativeTime } from "@/lib/utils";

export default function Proposals() {
  const [status, setStatus] = useState("");
  const q = useQuery({ queryKey: ["proposals", status], queryFn: () => api(`/proposals?page_size=100${status ? `&status=${status}` : ""}`) });
  return (
    <>
      <PageHeader title="Proposals" description="Draft → In review → Approved → Sent → Accepted / Rejected." actions={
        <Select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)} className="w-44">
          <option value="">All statuses</option>{["draft", "in_review", "approved", "sent", "accepted", "rejected"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}</Select>} />
      <QueryView q={q}>
        {(d: any) => d.items.length === 0 ? <EmptyState title="No proposals" body="Generate one from a reviewed architecture." /> : (
          <Card><Table><thead><tr><Th>Proposal</Th><Th>Organisation</Th><Th>Status</Th><Th>Version</Th><Th>Estimate</Th><Th>Updated</Th></tr></thead><tbody>
            {d.items.map((p: any) => <tr key={p.id} className="hover:bg-muted/40"><Td><Link className="font-medium hover:underline" href={`/app/proposals/${p.id}`}>{p.title}</Link></Td><Td>{p.organisation_name}</Td>
              <Td><StatusBadge status={p.status} /></Td><Td>v{p.current_version}</Td><Td>{money(p.total_estimate, p.currency)}</Td><Td className="text-xs">{relativeTime(p.updated_at)}</Td></tr>)}
          </tbody></Table></Card>
        )}
      </QueryView>
    </>
  );
}
