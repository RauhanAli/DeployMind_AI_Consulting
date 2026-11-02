"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { use } from "react";

import { PageHeader, QueryView } from "@/components/app/common";
import { AssessmentReport, AssessmentWizard } from "@/components/domain/assessment";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AssessmentDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const qc = useQueryClient();
  const { can } = useAuth();
  const q = useQuery({ queryKey: ["assessment", id], queryFn: () => api(`/assessments/${id}`) });
  return (
    <QueryView q={q}>
      {(a: any) => (
        <>
          <PageHeader title={`${a.profile?.company_name ?? "Assessment"} · AI readiness`} back={{ href: "/app/assessments", label: "Assessments" }} />
          {a.status === "draft" ? <AssessmentWizard id={id} onDone={() => qc.invalidateQueries({ queryKey: ["assessment", id] })} /> : <AssessmentReport id={id} canRegenerate={can("assessment.write")} />}
        </>
      )}
    </QueryView>
  );
}
