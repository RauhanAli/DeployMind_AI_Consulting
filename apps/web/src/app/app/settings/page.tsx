"use client";

import { useQuery } from "@tanstack/react-query";

import { KeyValue, PageHeader, QueryView } from "@/components/app/common";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { money } from "@/lib/utils";

export default function SettingsPage() {
  const q = useQuery({ queryKey: ["settings"], queryFn: () => api("/settings") });
  const agents = useQuery({ queryKey: ["agents"], queryFn: () => api<any[]>("/agents") });
  return (
    <>
      <PageHeader title="Settings" description="Platform configuration. Secrets are managed via environment variables and the encrypted secret store — never shown here." />
      <QueryView q={q} rows={5}>
        {(s: any) => (
          <div className="grid gap-4 xl:grid-cols-2">
            <Card><CardHeader><CardTitle>AI providers</CardTitle><CardDescription>Default provider: <strong>{s.ai.provider}</strong>{s.ai.mock_mode && " (mock mode active)"} · embeddings {s.ai.embedding_provider} ({s.ai.embedding_dimensions}d)</CardDescription></CardHeader>
              <CardContent><Table><tbody>{s.ai.providers.map((p: any) => <tr key={p.provider}><Td className="font-mono">{p.provider}</Td><Td>{p.default_model ?? p.description}</Td><Td>{p.configured ? <Badge tone="success">Configured</Badge> : <Badge>No API key</Badge>}</Td></tr>)}</tbody></Table>
                <p className="mt-2 text-xs text-muted-foreground">Set OPENAI_API_KEY / ANTHROPIC_API_KEY and AI_PROVIDER in the API environment to enable real models.</p></CardContent></Card>
            <Card><CardHeader><CardTitle>Deployment adapters</CardTitle></CardHeader><CardContent className="space-y-2">{s.deployment_adapters.map((a: any) => (
              <div key={a.adapter} className="flex items-start justify-between gap-3 text-sm"><div><p className="font-mono">{a.adapter}</p><p className="text-xs text-muted-foreground">{a.reason ?? a.label}</p></div>{a.available ? <Badge tone="success">Available</Badge> : <Badge>Not configured</Badge>}</div>))}</CardContent></Card>
            <Card><CardHeader><CardTitle>Opportunity weights</CardTitle><CardDescription>Edit on the Opportunities page.</CardDescription></CardHeader><CardContent><KeyValue items={Object.entries(s.opportunity_weights).map(([k, v]) => [k.replace(/_/g, " "), String(v)])} /></CardContent></Card>
            <Card><CardHeader><CardTitle>Rate card (proposal estimator)</CardTitle></CardHeader><CardContent><KeyValue items={[...Object.entries(s.rate_card.roles).map(([k, v]) => [k, `${money(v as number)} / day`] as [string, string]),
              ["Infrastructure estimate", money(s.rate_card.infrastructure_estimate)], ["Support", `${money(s.rate_card.support_monthly)} × ${s.rate_card.support_months} months`]]} /></CardContent></Card>
            <Card className="xl:col-span-2"><CardHeader><CardTitle>AI agents</CardTitle><CardDescription>Each agent has typed I/O, an explicit tool allowlist, bounded retries and usage tracking. Business rules stay in deterministic services.</CardDescription></CardHeader>
              <CardContent><QueryView q={agents}>{(list) => (
                <Table><thead><tr><Th>Agent</Th><Th>Responsibility</Th><Th>Tools</Th><Th>Output</Th></tr></thead><tbody>
                  {list.map((a) => <tr key={a.name}><Td className="font-mono text-xs">{a.name}</Td><Td className="text-sm">{a.responsibility}</Td><Td>{a.tools.length ? a.tools.map((t: string) => <Badge key={t} className="mr-1">{t}</Badge>) : <span className="text-xs text-muted-foreground">none</span>}</Td><Td className="font-mono text-xs">{a.output_schema}</Td></tr>)}
                </tbody></Table>)}</QueryView></CardContent></Card>
          </div>
        )}
      </QueryView>
    </>
  );
}
