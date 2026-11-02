"use client";

import { label } from "@deploymind/shared";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { EmptyState, PageHeader, QueryView } from "@/components/app/common";
import { OpportunityTable } from "@/components/domain/assessment";
import { OpportunityMatrix } from "@/components/domain/charts";
import { OrgSelect } from "@/components/domain/widgets";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function WeightsEditor({ orgId }: { orgId: string }) {
  const qc = useQueryClient();
  const { can } = useAuth();
  const s = useQuery({ queryKey: ["settings"], queryFn: () => api("/settings") });
  const [w, setW] = useState<Record<string, number>>({});
  useEffect(() => { if (s.data) setW(s.data.opportunity_weights); }, [s.data]);
  const save = useMutation({
    mutationFn: async () => {
      await api("/settings/opportunity_weights", { method: "PUT", body: { value: w } });
      return api(`/organisations/${orgId}/opportunities/rerank`, { method: "POST" });
    },
    onSuccess: () => { toast.success("Weights saved and opportunities re-ranked"); qc.invalidateQueries({ queryKey: ["opportunities"] }); qc.invalidateQueries({ queryKey: ["settings"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const total = Object.values(w).reduce((a, b) => a + Number(b || 0), 0);
  return (
    <Card>
      <CardHeader><CardTitle>Scoring formula</CardTitle>
        <CardDescription>priority = Σ(weight × factor) / (5 × Σ weights) × 100. Factors are 1–5; complexity, integration, risk and effort are inverted.</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        {Object.entries(w).map(([k, v]) => (
          <div key={k} className="grid grid-cols-[1fr_90px] items-center gap-3 text-sm">
            <label htmlFor={`w-${k}`}>{label(k)}</label>
            <Input id={`w-${k}`} type="number" step="0.05" min={0} value={v} disabled={!can("settings.manage")} onChange={(e) => setW({ ...w, [k]: Number(e.target.value) })} />
          </div>
        ))}
        <p className="text-xs text-muted-foreground">Sum of weights: {total.toFixed(2)}</p>
        {can("settings.manage") ? <Button onClick={() => save.mutate()} loading={save.isPending} disabled={total <= 0}>Save & re-rank</Button> :
          <p className="text-xs text-muted-foreground">Only super admins can change platform-wide weights.</p>}
      </CardContent>
    </Card>
  );
}

export default function Opportunities() {
  const [org, setOrg] = useState("");
  const q = useQuery({ queryKey: ["opportunities", org], queryFn: () => api<any[]>(`/opportunities${org ? `?organisation_id=${org}` : ""}`), enabled: !!org });
  return (
    <>
      <PageHeader title="Opportunity discovery" description="Opportunities generated from each organisation's assessment and ranked deterministically." actions={<OrgSelect value={org} onChange={setOrg} />} />
      {!org ? <EmptyState title="Choose an organisation" body="Select a customer to view their opportunity matrix." /> : (
        <QueryView q={q}>
          {(d) => d.length === 0 ? <EmptyState title="No opportunities yet" body="They are generated when the organisation submits an assessment." /> : (
            <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
              <div className="space-y-6"><OpportunityMatrix opportunities={d} /><OpportunityTable opportunities={d} /></div>
              <WeightsEditor orgId={org} />
            </div>
          )}
        </QueryView>
      )}
    </>
  );
}
