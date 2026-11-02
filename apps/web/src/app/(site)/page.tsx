import { ArrowRight, BarChart3, CheckCircle2, Hammer, LineChart, Lock, Rocket, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";

import { CtaBand, SectionHeading } from "@/components/site/chrome";
import { Badge, Button, Card, CardContent } from "@/components/ui";
import { CASE_STUDIES, ILLUSTRATIVE_METRICS, SERVICES, USE_CASES } from "@/lib/content";
import { ICONS } from "@/lib/icons";

const METHOD = [
  { icon: BarChart3, step: "Assess", title: "Find the right first project",
    body: "Deterministic readiness scoring, opportunity prioritisation and technical discovery with your stakeholders.",
    points: ["Readiness score across six dimensions", "Ranked opportunity matrix", "Approved requirements"] },
  { icon: Hammer, step: "Build", title: "Engineer it with your systems",
    body: "Forward deployed engineers design, integrate and build alongside your team with weekly evaluated demos.",
    points: ["Reviewed solution architecture", "Integrations with credential vaulting", "Grounded RAG with citations"] },
  { icon: Rocket, step: "Run", title: "Deploy, monitor and own it",
    body: "Staged releases with approval gates and rollback, live telemetry, evaluation runs and incident response.",
    points: ["Dev → staging → production", "Latency, tokens and cost tracked", "Incidents and SLA-backed support"] },
];

const STACK = ["OpenAI", "Anthropic Claude", "PostgreSQL + pgvector", "LangGraph", "FastAPI", "Next.js", "Docker", "AWS ECS", "Redis", "OpenTelemetry", "GitHub Actions", "Terraform"];

export default function HomePage() {
  return (
    <>
      <section className="relative overflow-hidden border-b">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(60rem_30rem_at_70%_-10%,var(--accent),transparent)]" />
        <div className="container-page grid gap-12 py-20 md:py-28 lg:grid-cols-[1.2fr_1fr] lg:items-center">
          <div className="space-y-7 fade-up">
            <Badge tone="primary" className="px-3 py-1 text-sm"><Sparkles className="size-3.5" /> Forward deployed AI engineering</Badge>
            <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl lg:text-6xl">
              From AI prototype to production-ready enterprise systems.
            </h1>
            <p className="max-w-xl text-lg text-muted-foreground">
              DeployMind assesses where AI will create value, builds it into your systems with your data and permissions,
              and runs it in production with monitoring, evaluation and accountable ownership.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button asChild size="lg"><Link href="/ai-readiness">Take the AI readiness assessment <ArrowRight /></Link></Button>
              <Button asChild size="lg" variant="outline"><Link href="/book-discovery-call">Book a discovery call</Link></Button>
            </div>
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
              {["Explainable scoring", "Citations on every answer", "Approval-gated releases"].map((t) => (
                <span key={t} className="flex items-center gap-1.5"><CheckCircle2 className="size-4 text-success" />{t}</span>
              ))}
            </div>
          </div>
          <Card className="fade-up shadow-lg">
            <CardContent className="space-y-4 p-6">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Engagement journey</span>
                <Badge tone="success">Live in production</Badge>
              </div>
              {[["Assessment", "Readiness 54/100 · Developing", 100], ["Discovery", "12 requirements approved", 100],
                ["Proposal", "Accepted by customer", 100], ["Build", "Grounded assistant + integrations", 100],
                ["Deploy", "v1.0.2 · production · healthy", 100], ["Run", "Evaluations passing · 1 incident resolved", 80]].map(([k, v, p]) => (
                <div key={k as string} className="space-y-1.5">
                  <div className="flex justify-between text-sm"><span className="font-medium">{k}</span><span className="text-muted-foreground">{v}</span></div>
                  <div className="h-1.5 rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${p}%` }} /></div>
                </div>
              ))}
              <p className="text-xs text-muted-foreground">Example journey from the seeded demo customer (fictional).</p>
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="container-page py-20">
        <SectionHeading eyebrow="Services" title="Everything between an AI idea and an operated system" />
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {SERVICES.map((s) => {
            const Icon = ICONS[s.icon as keyof typeof ICONS];
            return (
              <Link key={s.slug} href={`/${s.slug}`} className="group rounded-xl border bg-card p-6 transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md">
                <Icon className="size-6 text-primary" />
                <h3 className="mt-4 font-semibold">{s.name}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{s.short}</p>
                <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-primary">Learn more <ArrowRight className="size-4 transition group-hover:translate-x-0.5" /></span>
              </Link>
            );
          })}
        </div>
      </section>

      <section className="border-y bg-muted/40">
        <div className="container-page py-20">
          <SectionHeading eyebrow="Methodology" title="Assess → Build → Run" intro="One accountable team from the first workshop to the on-call rota." />
          <div className="mt-12 grid gap-6 lg:grid-cols-3">
            {METHOD.map((m) => (
              <Card key={m.step} className="relative">
                <CardContent className="space-y-4 p-6">
                  <div className="flex items-center gap-3">
                    <span className="flex size-10 items-center justify-center rounded-lg bg-accent text-accent-foreground"><m.icon className="size-5" /></span>
                    <span className="text-sm font-semibold uppercase tracking-wide text-primary">{m.step}</span>
                  </div>
                  <h3 className="text-xl font-semibold">{m.title}</h3>
                  <p className="text-sm text-muted-foreground">{m.body}</p>
                  <ul className="space-y-2">
                    {m.points.map((p) => <li key={p} className="flex gap-2 text-sm"><CheckCircle2 className="mt-0.5 size-4 text-success" />{p}</li>)}
                  </ul>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <section className="container-page py-20">
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
          <div className="space-y-5">
            <SectionHeading eyebrow="Engineering principles" title="Production AI, without the hand-waving" />
            {[[ShieldCheck, "Business rules stay deterministic", "Scores, permissions, approvals and costs are computed by code. LLMs explain and draft — they never decide."],
              [Lock, "Tenant isolation by construction", "Every query is scoped to an organisation; retrieval applies document permissions inside the database."],
              [LineChart, "Measured, not assumed", "Evaluation datasets, regression alerts and real telemetry separate demo numbers from production numbers."]].map(([Icon, t, b]) => {
              const I = Icon as typeof ShieldCheck;
              return (
                <div key={t as string} className="flex gap-4">
                  <I className="mt-1 size-5 shrink-0 text-primary" />
                  <div><h3 className="font-semibold">{t as string}</h3><p className="text-sm text-muted-foreground">{b as string}</p></div>
                </div>
              );
            })}
          </div>
          <div>
            <p className="mb-4 text-sm font-medium text-muted-foreground">Technology ecosystem</p>
            <div className="flex flex-wrap gap-2">
              {STACK.map((s) => <span key={s} className="rounded-lg border bg-card px-3 py-2 text-sm">{s}</span>)}
            </div>
            <div className="mt-8 grid grid-cols-2 gap-4">
              {ILLUSTRATIVE_METRICS.map((m) => (
                <div key={m.label} className="rounded-xl border bg-card p-5">
                  <div className="text-3xl font-semibold tracking-tight text-primary">{m.value}</div>
                  <div className="mt-1 text-sm text-muted-foreground">{m.label}</div>
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs text-muted-foreground">Platform capabilities — not customer outcome claims.</p>
          </div>
        </div>
      </section>

      <section className="border-y bg-muted/40">
        <div className="container-page py-20">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <SectionHeading eyebrow="Use cases" title="Where AI earns its keep" />
            <Button asChild variant="outline"><Link href="/use-cases">All use cases</Link></Button>
          </div>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {USE_CASES.slice(0, 4).map((u) => (
              <Card key={u.title}><CardContent className="space-y-2 p-5">
                <Badge>{u.industry}</Badge><h3 className="font-semibold">{u.title}</h3><p className="text-sm text-muted-foreground">{u.body}</p>
              </CardContent></Card>
            ))}
          </div>
        </div>
      </section>

      <section className="container-page py-20">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <SectionHeading eyebrow="Case studies" title="Synthetic examples of the work" intro="Illustrative engagements showing how we approach delivery. Figures are illustrative, not client results." />
          <Button asChild variant="outline"><Link href="/case-studies">Read case studies</Link></Button>
        </div>
        <div className="mt-10 grid gap-5 lg:grid-cols-3">
          {CASE_STUDIES.map((c) => (
            <Card key={c.slug}><CardContent className="space-y-3 p-6">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{c.client}</p>
              <h3 className="text-lg font-semibold">{c.title}</h3>
              <p className="text-sm text-muted-foreground">{c.challenge}</p>
              <div className="grid grid-cols-3 gap-2 border-t pt-3">
                {c.results.map(([v, l]) => <div key={l}><div className="font-semibold text-primary">{v}</div><div className="text-[11px] leading-tight text-muted-foreground">{l}</div></div>)}
              </div>
            </CardContent></Card>
          ))}
        </div>
      </section>
      <CtaBand />
    </>
  );
}
