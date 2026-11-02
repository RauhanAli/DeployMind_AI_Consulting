"use client";

import { useQuery } from "@tanstack/react-query";
import { use } from "react";

import { PageHeader, QueryView, StatCard, StatusBadge } from "@/components/app/common";
import { Badge, Card, CardContent, CardHeader, CardTitle, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime, pct, usd } from "@/lib/utils";

export default function EvalRun({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const q = useQuery({ queryKey: ["run", id], queryFn: () => api(`/evaluations/runs/${id}`),
    refetchInterval: (q) => (["queued", "running"].includes(q.state.data?.run?.status) ? 2000 : false) });
  return (
    <QueryView q={q} rows={6}>
      {({ run, results }: any) => (
        <>
          <PageHeader title={run.label} back={{ href: `/app/evaluations?app=${run.app_id}`, label: "Evaluations" }}
            description={<span className="flex flex-wrap items-center gap-2"><StatusBadge status={run.status} />{run.config.provider}:{run.config.model} · prompt {run.config.prompt_version} · judge {run.judge} · {formatDateTime(run.finished_at ?? run.created_at)}</span>} />
          {run.error && <p className="mb-4 rounded-md bg-danger/10 p-3 text-sm text-danger">{run.error}</p>}
          {run.regressions.length > 0 && (
            <div className="mb-4 rounded-lg border border-danger/30 bg-danger/5 p-3 text-sm"><strong className="text-danger">Regression alert</strong> vs baseline:
              <ul className="mt-1 list-disc pl-5">{run.regressions.map((r: any) => <li key={r.metric}>{r.metric}: {r.baseline} → {r.current} ({r.delta})</li>)}</ul></div>
          )}
          <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <StatCard label="Pass rate" value={pct(run.metrics.pass_rate)} hint={`${run.metrics.cases ?? 0} cases`} />
            <StatCard label="Correctness" value={run.metrics.correctness ?? "—"} />
            <StatCard label="Faithfulness" value={run.metrics.faithfulness ?? "—"} />
            <StatCard label="Retrieval P / R" value={`${run.metrics.retrieval_precision ?? "—"} / ${run.metrics.retrieval_recall ?? "—"}`} />
            <StatCard label="Latency P95 · cost" value={`${run.metrics.latency_p95_ms ?? "—"} ms`} hint={usd(run.metrics.total_cost_usd, 4)} />
          </div>
          <Card><CardHeader><CardTitle>Per-case results</CardTitle></CardHeader><CardContent>
            <Table><thead><tr><Th>Question</Th><Th>Answer</Th><Th>Metrics</Th><Th>Result</Th></tr></thead><tbody>
              {results.map((r: any) => (
                <tr key={r.id} className="align-top">
                  <Td className="max-w-xs font-medium">{r.question}</Td>
                  <Td className="max-w-md text-xs">{r.answer}<p className="mt-1 text-muted-foreground">cited: {r.cited_sources.join(", ") || "none"} · retrieved: {r.retrieved_sources.join(", ") || "none"}</p></Td>
                  <Td className="text-[11px]">{["correctness", "faithfulness", "citation_quality", "retrieval_precision", "retrieval_recall"].map((k) => <div key={k}>{k.replace(/_/g, " ")}: <span className="font-mono">{r.metrics[k]}</span></div>)}
                    {r.metrics.judge && <div className="mt-1"><Badge tone="primary">judge</Badge> c={r.metrics.judge.correctness} f={r.metrics.judge.faithfulness}</div>}</Td>
                  <Td>{r.passed ? <Badge tone="success">Pass</Badge> : <Badge tone="danger">Fail</Badge>}</Td>
                </tr>
              ))}
            </tbody></Table>
          </CardContent></Card>
        </>
      )}
    </QueryView>
  );
}
