"use client";

import { useQuery } from "@tanstack/react-query";

import { EmptyState, PageHeader, QueryView } from "@/components/app/common";
import { OpportunityTable } from "@/components/domain/assessment";
import { OpportunityMatrix } from "@/components/domain/charts";
import { api } from "@/lib/api";

export default function PortalOpportunities() {
  const q = useQuery({ queryKey: ["opportunities"], queryFn: () => api<any[]>("/opportunities") });
  return (
    <>
      <PageHeader title="AI opportunities" description="Identified from your readiness assessment and ranked by impact and feasibility." />
      <QueryView q={q}>
        {(d) => d.length === 0 ? <EmptyState title="No opportunities yet" body="Complete an AI readiness assessment to see your prioritised opportunities." /> : (
          <div className="space-y-6"><OpportunityMatrix opportunities={d} /><OpportunityTable opportunities={d} /></div>
        )}
      </QueryView>
    </>
  );
}
