"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { EmptyState, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { Card, Input, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";

export default function Organisations() {
  const [q, setQ] = useState("");
  const orgs = useQuery({ queryKey: ["orgs", q], queryFn: () => api(`/organisations?page_size=100${q ? `&q=${encodeURIComponent(q)}` : ""}`) });
  return (
    <>
      <PageHeader title="Organisations" description="Customer tenants. Each organisation's data is isolated." />
      <Input placeholder="Search by name or industry…" value={q} onChange={(e) => setQ(e.target.value)} className="mb-4 max-w-sm" aria-label="Search organisations" />
      <QueryView q={orgs}>
        {(d: any) => d.items.length === 0 ? <EmptyState title="No organisations found" /> : (
          <Card><Table><thead><tr><Th>Organisation</Th><Th>Industry</Th><Th>Pipeline</Th><Th>Readiness</Th><Th>Active projects</Th><Th>Since</Th></tr></thead><tbody>
            {d.items.map((o: any) => (
              <tr key={o.id} className="hover:bg-muted/40">
                <Td><Link href={`/app/organisations/${o.id}`} className="font-medium hover:underline">{o.name}</Link>{o.is_demo && <span className="ml-2 text-xs text-muted-foreground">demo</span>}</Td>
                <Td>{o.industry ?? "—"}</Td><Td><StatusBadge status={o.lead_status} /></Td><Td>{o.readiness_score ?? "—"}</Td><Td>{o.active_projects}</Td><Td className="text-xs">{formatDate(o.created_at)}</Td>
              </tr>
            ))}
          </tbody></Table></Card>
        )}
      </QueryView>
    </>
  );
}
