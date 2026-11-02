"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { EmptyState, PageHeader, QueryView, StatusBadge } from "@/components/app/common";
import { StartAssessmentButton } from "@/components/domain/assessment";
import { Card, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDate } from "@/lib/utils";

export default function PortalAssessments() {
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["assessments"], queryFn: () => api("/assessments") });
  return (
    <>
      <PageHeader title="AI readiness assessments" description="Six dimensions, weighted and scored deterministically."
        actions={can("assessment.write") && <StartAssessmentButton base="/portal/assessments" />} />
      <QueryView q={q}>
        {(d: any) => d.items.length === 0 ? <EmptyState title="No assessments yet" body="Take 10 minutes to assess your AI readiness." action={can("assessment.write") && <StartAssessmentButton base="/portal/assessments" />} /> : (
          <Card><Table><thead><tr><Th>Started</Th><Th>Status</Th><Th>Score</Th><Th>Classification</Th><Th /></tr></thead><tbody>
            {d.items.map((a: any) => (
              <tr key={a.id}><Td>{formatDate(a.created_at)}</Td><Td><StatusBadge status={a.status} /></Td>
                <Td className="font-semibold">{a.overall_score ?? "—"}</Td><Td>{a.classification ?? "—"}</Td>
                <Td className="text-right"><Link className="text-primary hover:underline" href={`/portal/assessments/${a.id}`}>{a.status === "draft" ? "Continue" : "View report"}</Link></Td></tr>
            ))}
          </tbody></Table></Card>
        )}
      </QueryView>
    </>
  );
}
