"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader, QueryView, StatCard, StatusBadge } from "@/components/app/common";
import { HBar, TimeSeries } from "@/components/domain/charts";
import { OrgSelect } from "@/components/domain/widgets";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Progress, Select, Table, Td, Th } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { compact, usd } from "@/lib/utils";

export default function Costs() {
  const qc = useQueryClient();
  const { can } = useAuth();
  const [days, setDays] = useState(30);
  const [demo, setDemo] = useState(true);
  const q = useQuery({ queryKey: ["costs", days, demo], queryFn: () => api(`/costs/summary?days=${days}&include_demo=${demo}`) });
  const budgets = useQuery({ queryKey: ["budgets"], queryFn: () => api<any[]>("/costs/budgets") });
  const pricing = useQuery({ queryKey: ["pricing"], queryFn: () => api<any[]>("/costs/pricing") });
  const [b, setB] = useState({ organisation_id: "", monthly_limit_usd: "", alert_threshold_pct: "80" });
  const [p, setP] = useState({ provider: "openai", model: "", input_per_million: "", output_per_million: "" });
  const saveB = useMutation({ mutationFn: () => api("/costs/budgets", { method: "POST", body: { ...b, monthly_limit_usd: Number(b.monthly_limit_usd), alert_threshold_pct: Number(b.alert_threshold_pct) } }),
    onSuccess: () => { toast.success("Budget saved"); qc.invalidateQueries({ queryKey: ["budgets"] }); }, onError: (e) => toast.error(errorMessage(e)) });
  const check = useMutation({ mutationFn: () => api("/costs/budgets/check", { method: "POST" }), onSuccess: (r) => toast.info(`${r.alerts_raised} alert(s) raised`), onError: (e) => toast.error(errorMessage(e)) });
  const saveP = useMutation({ mutationFn: () => api("/costs/pricing", { method: "POST", body: { ...p, input_per_million: Number(p.input_per_million), output_per_million: Number(p.output_per_million) } }),
    onSuccess: () => { toast.success("Pricing saved — applies to new usage"); qc.invalidateQueries({ queryKey: ["pricing"] }); }, onError: (e) => toast.error(errorMessage(e)) });
  return (
    <>
      <PageHeader title="Cost management" description="Token usage and estimated model cost by organisation, project, model and agent."
        actions={<>
          <Select aria-label="Window" value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-36">{[7, 30, 90].map((d) => <option key={d} value={d}>Last {d} days</option>)}</Select>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} /> Include demo usage</label></>} />
      <QueryView q={q} rows={5}>
        {(c: any) => (
          <div className="space-y-6">
            <p className="text-xs text-muted-foreground">{c.label}. {demo ? "Includes seeded demo usage." : "Excludes seeded demo usage."}</p>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Estimated cost" value={usd(c.totals.estimated_cost_usd)} />
              <StatCard label="Model requests" value={compact(c.totals.requests)} hint={`${c.totals.mock_requests} via mock provider ($0)`} />
              <StatCard label="Input tokens" value={compact(c.totals.input_tokens)} />
              <StatCard label="Output tokens" value={compact(c.totals.output_tokens)} />
            </div>
            <div className="grid gap-4 xl:grid-cols-2">
              <TimeSeries title="Daily estimated cost" data={c.daily} xKey="date" series={[{ key: "cost_usd", label: "Cost" }]} kind="bar" format={(v) => `$${v.toFixed(2)}`} />
              <TimeSeries title="Daily tokens" data={c.daily} xKey="date" series={[{ key: "input_tokens", label: "Input" }, { key: "output_tokens", label: "Output" }]} kind="area" />
              <HBar title="Cost by organisation" data={c.by_organisation} valueKey="cost_usd" labelKey="name" format={(v) => `$${v.toFixed(2)}`} />
              <HBar title="Cost by project" data={c.by_project} valueKey="cost_usd" labelKey="name" format={(v) => `$${v.toFixed(2)}`} />
            </div>
            <div className="grid gap-4 xl:grid-cols-2">
              <Card><CardHeader><CardTitle className="text-sm">By model</CardTitle></CardHeader><CardContent><Table><thead><tr><Th>Model</Th><Th>Op</Th><Th>Requests</Th><Th>Tokens in/out</Th><Th>Cost</Th></tr></thead><tbody>
                {c.by_model.map((m: any) => <tr key={m.provider + m.model + m.operation}><Td className="font-mono text-xs">{m.provider}:{m.model}</Td><Td>{m.operation}</Td><Td>{m.requests}</Td><Td>{compact(m.input_tokens)}/{compact(m.output_tokens)}</Td><Td>{usd(m.cost_usd)}</Td></tr>)}</tbody></Table></CardContent></Card>
              <Card><CardHeader><CardTitle className="text-sm">By agent</CardTitle></CardHeader><CardContent><Table><thead><tr><Th>Agent</Th><Th>Requests</Th><Th>Tokens</Th><Th>Cost</Th></tr></thead><tbody>
                {c.by_agent.map((a: any) => <tr key={a.agent}><Td className="font-mono text-xs">{a.agent}</Td><Td>{a.requests}</Td><Td>{compact(a.tokens)}</Td><Td>{usd(a.cost_usd)}</Td></tr>)}</tbody></Table>
                <p className="mt-2 text-xs text-muted-foreground">Monthly: {c.monthly.map((m: any) => `${m.month} ${usd(m.cost_usd)}`).join(" · ")}</p></CardContent></Card>
            </div>
          </div>
        )}
      </QueryView>
      <div className="mt-6 grid gap-4 xl:grid-cols-2">
        <Card><CardHeader className="flex-row items-center justify-between"><div><CardTitle>Budgets & alerts</CardTitle><CardDescription>Alerts fire once per threshold per month (checked every 15 minutes).</CardDescription></div>
          {can("cost.manage") && <Button size="sm" variant="outline" onClick={() => check.mutate()} loading={check.isPending}>Check now</Button>}</CardHeader>
          <CardContent className="space-y-4">
            <QueryView q={budgets}>{(list) => list.map((x) => (
              <div key={x.id} className="space-y-1 text-sm"><div className="flex justify-between"><span>{x.organisation_name}</span><span>{usd(x.spend_usd)} / {usd(x.monthly_limit_usd, 0)} <StatusBadge status={x.state === "ok" ? "on_track" : x.state === "warning" ? "at_risk" : "breached"} /></span></div>
                <Progress value={x.percent} tone={x.state === "ok" ? "success" : x.state === "warning" ? "warning" : "danger"} /></div>))}
            </QueryView>
            {can("cost.manage") && (
              <form className="grid gap-2 border-t pt-3 sm:grid-cols-4" onSubmit={(e) => { e.preventDefault(); saveB.mutate(); }}>
                <div className="sm:col-span-2"><OrgSelect value={b.organisation_id} onChange={(v) => setB({ ...b, organisation_id: v })} /></div>
                <Input type="number" min={1} placeholder="USD / month" value={b.monthly_limit_usd} onChange={(e) => setB({ ...b, monthly_limit_usd: e.target.value })} aria-label="Monthly limit" />
                <Input type="number" min={10} max={100} placeholder="Alert %" value={b.alert_threshold_pct} onChange={(e) => setB({ ...b, alert_threshold_pct: e.target.value })} aria-label="Alert threshold" />
                <Button type="submit" size="sm" className="sm:col-span-4" disabled={!b.organisation_id || !b.monthly_limit_usd} loading={saveB.isPending}>Save budget</Button>
              </form>
            )}
          </CardContent></Card>
        <Card><CardHeader><CardTitle>Provider pricing</CardTitle><CardDescription>USD per million tokens. Verify against providers&apos; current price lists; changes apply to new usage.</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            <QueryView q={pricing}>{(list) => (
              <Table><thead><tr><Th>Model</Th><Th>Input</Th><Th>Output</Th><Th>From</Th></tr></thead><tbody>
                {list.map((x) => <tr key={x.id}><Td className="font-mono text-xs">{x.provider}:{x.model}</Td><Td>${x.input_per_million}</Td><Td>${x.output_per_million}</Td><Td className="text-xs">{x.effective_from}</Td></tr>)}</tbody></Table>)}
            </QueryView>
            {can("cost.manage") && (
              <form className="grid gap-2 border-t pt-3 sm:grid-cols-4" onSubmit={(e) => { e.preventDefault(); saveP.mutate(); }}>
                <Select aria-label="Provider" value={p.provider} onChange={(e) => setP({ ...p, provider: e.target.value })}><option>openai</option><option>anthropic</option><option>mock</option></Select>
                <Input placeholder="model" value={p.model} onChange={(e) => setP({ ...p, model: e.target.value })} aria-label="Model" />
                <Input type="number" step="0.01" min={0} placeholder="input $/M" value={p.input_per_million} onChange={(e) => setP({ ...p, input_per_million: e.target.value })} aria-label="Input price" />
                <Input type="number" step="0.01" min={0} placeholder="output $/M" value={p.output_per_million} onChange={(e) => setP({ ...p, output_per_million: e.target.value })} aria-label="Output price" />
                <Button type="submit" size="sm" className="sm:col-span-4" disabled={!p.model || p.input_per_million === "" || p.output_per_million === ""} loading={saveP.isPending}>Save pricing</Button>
              </form>
            )}
          </CardContent></Card>
      </div>
    </>
  );
}
