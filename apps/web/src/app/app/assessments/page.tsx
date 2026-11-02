"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { EmptyState, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { StartAssessmentButton } from "@/components/domain/assessment";
import { OrgSelect } from "@/components/domain/widgets";
import { Card, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";

export default function Assessments() {
  const [org, setOrg] = useState("");
  const q = useQuery({ queryKey: ["assessments", org], queryFn: () => api(`/assessments?page_size=100${org ? `&organisation_id=${org}` : ""}`) });
  return (
    <>
      <PageHeader title="Assessments" description="AI readiness assessments across all customers."
        actions={<><OrgSelect value={org} onChange={setOrg} allowAll />{org && <StartAssessmentButton orgId={org} base="/app/assessments" />}</>} />
      <QueryView q={q}>
        {(d: any) => d.items.length === 0 ? <EmptyState title="No assessments" /> : (
          <Card><Table><thead><tr><Th>Organisation</Th><Th>Status</Th><Th>Score</Th><Th>Classification</Th><Th>Report</Th><Th>Submitted</Th></tr></thead><tbody>
            {d.items.map((a: any) => (
              <tr key={a.id} className="hover:bg-muted/40"><Td><Link className="font-medium hover:underline" href={`/app/assessments/${a.id}`}>{a.organisation_name}</Link></Td>
                <Td><StatusBadge status={a.status} /></Td><Td className="font-semibold">{a.overall_score ?? "—"}</Td><Td>{a.classification ?? "—"}</Td>
                <Td><StatusBadge status={a.report_status === "none" ? null : a.report_status} /></Td><Td className="text-xs">{formatDate(a.submitted_at)}</Td></tr>
            ))}
          </tbody></Table></Card>
        )}
      </QueryView>
    </>
  );
}
