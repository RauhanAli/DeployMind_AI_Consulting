"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { use } from "react";

import { PageHeader, QueryView } from "@/components/app/common";
import { AssessmentReport, AssessmentWizard } from "@/components/domain/assessment";
import { api } from "@/lib/api";

export default function PortalAssessment({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["assessment", id], queryFn: () => api(`/assessments/${id}`) });
  return (
    <QueryView q={q}>
      {(a: any) => (
        <>
          <PageHeader title={a.status === "draft" ? "AI readiness assessment" : "Your AI readiness report"} back={{ href: "/portal/assessments", label: "Assessments" }}
            description={a.status === "draft" ? "Answer at your own pace — progress is saved." : `Submitted ${new Date(a.submitted_at).toLocaleDateString()}`} />
          {a.status === "draft" ? <AssessmentWizard id={id} onDone={() => qc.invalidateQueries({ queryKey: ["assessment", id] })} /> : <AssessmentReport id={id} />}
        </>
      )}
    </QueryView>
  );
}
