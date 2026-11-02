"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { EmptyState, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { Card, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate, money } from "@/lib/utils";

export default function PortalProposals() {
  const q = useQuery({ queryKey: ["proposals"], queryFn: () => api("/proposals") });
  return (
    <>
      <PageHeader title="Proposals" description="Commercial and technical proposals shared with you for review." />
      <QueryView q={q}>
        {(d: any) => d.items.length === 0 ? <EmptyState title="No proposals yet" body="Proposals appear here once our team has reviewed and sent them." /> : (
          <Card><Table><thead><tr><Th>Proposal</Th><Th>Status</Th><Th>Estimate</Th><Th>Sent</Th><Th /></tr></thead><tbody>
            {d.items.map((p: any) => (
              <tr key={p.id}><Td className="font-medium">{p.title}</Td><Td><StatusBadge status={p.status} /></Td><Td>{money(p.total_estimate, p.currency)}</Td>
                <Td>{formatDate(p.sent_at)}</Td><Td className="text-right"><Link className="text-primary hover:underline" href={`/portal/proposals/${p.id}`}>{p.status === "sent" ? "Review" : "View"}</Link></Td></tr>
            ))}
          </tbody></Table></Card>
        )}
      </QueryView>
    </>
  );
}
