"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { EmptyState, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { Card, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";

export default function Architecture() {
  const q = useQuery({ queryKey: ["archs"], queryFn: () => api<any[]>("/architecture") });
  return (
    <>
      <PageHeader title="Solution design" description="Architecture documents generated from approved requirements, edited and peer-reviewed by engineers." />
      <QueryView q={q}>
        {(list) => list.length === 0 ? <EmptyState title="No architecture documents" body="Generate one from a discovery session with approved requirements." /> : (
          <Card><Table><thead><tr><Th>Document</Th><Th>Version</Th><Th>Status</Th><Th>Source</Th><Th>Created</Th></tr></thead><tbody>
            {list.map((a) => <tr key={a.id} className="hover:bg-muted/40"><Td><Link className="font-medium hover:underline" href={`/app/architecture/${a.id}`}>{a.title}</Link><p className="text-xs text-muted-foreground">{a.content.overview}</p></Td>
              <Td>v{a.version}</Td><Td><StatusBadge status={a.status} /></Td><Td>{a.source}</Td><Td className="text-xs">{formatDate(a.created_at)}</Td></tr>)}
          </tbody></Table></Card>
        )}
      </QueryView>
    </>
  );
}
