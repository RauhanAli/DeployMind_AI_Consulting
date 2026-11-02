"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Download, RefreshCw, Save } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer } from "recharts";
import { toast } from "sonner";

import { AiDraftNotice, ErrorState, Loading, StatusBadge } from "@/components/app/common";
import { CHART } from "@/components/domain/charts";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Field, Input, Progress, Select, Textarea } from "@/components/ui";
import { api, downloadFile, errorMessage, newIdempotencyKey } from "@/lib/api";
import { cn, money } from "@/lib/utils";

type Question = { key: string; dimension: string; text: string; help_text: string | null; qtype: "single" | "multi" | "scale";
  options: { value: string; label: string; score: number }[]; condition: { question: string; in: string[] } | null };

export function isApplicable(q: Question, answers: Record<string, any>): boolean {
  if (!q.condition) return true;
  const parent = answers[q.condition.question];
  if (parent === undefined || parent === null) return false;
  const vals = Array.isArray(parent) ? parent : [parent];
  return vals.some((v) => q.condition!.in.includes(v));
}

export function missingInStep(questions: Question[], answers: Record<string, any>, dimension: string): string[] {
  return questions.filter((q) => q.dimension === dimension && isApplicable(q, answers) && (answers[q.key] === undefined || (q.qtype === "multi" && !Array.isArray(answers[q.key])))).map((q) => q.key);
}

const SIZES = ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5000+"];

export function AssessmentWizard({ id, onDone }: { id: string; onDone: () => void }) {
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ["public-meta"], queryFn: () => api("/public/meta") });
  const questions = useQuery({ queryKey: ["questions"], queryFn: () => api<Question[]>("/assessments/questions") });
  const a = useQuery({ queryKey: ["assessment", id], queryFn: () => api(`/assessments/${id}`) });
  const [answers, setAnswers] = useState<Record<string, any>>({});
  const [profile, setProfile] = useState<Record<string, any>>({});
  const [step, setStep] = useState(0);
  const [showErrors, setShowErrors] = useState(false);
  const loaded = useRef(false);

  useEffect(() => {
    if (a.data && !loaded.current) {
      loaded.current = true;
      setAnswers(a.data.answers ?? {});
      setProfile(a.data.profile ?? {});
      setStep(Math.min(a.data.current_step ?? 0, (a.data.steps?.length ?? 8) - 1));
    }
  }, [a.data]);

  const save = useMutation({
    mutationFn: (s: number) => api(`/assessments/${id}/progress`, { method: "PUT", body: { answers, profile, current_step: s } }),
    onSuccess: (d) => { setAnswers(d.answers); qc.setQueryData(["assessment", id], d); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const submit = useMutation({
    mutationFn: async () => {
      await api(`/assessments/${id}/progress`, { method: "PUT", body: { answers, profile, current_step: steps.length - 1 } });
      return api(`/assessments/${id}/submit`, { method: "POST", idempotencyKey: newIdempotencyKey() });
    },
    onSuccess: () => { toast.success("Assessment submitted — your score has been calculated"); qc.invalidateQueries(); onDone(); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const steps: string[] = a.data?.steps ?? ["profile"];
  const dims: Record<string, { label: string; summary: string }> = useMemo(
    () => Object.fromEntries((meta.data?.dimensions ?? []).map((d: any) => [d.key, d])), [meta.data]);

  if (a.isPending || questions.isPending || meta.isPending) return <Loading rows={5} />;
  if (a.isError) return <ErrorState error={a.error} />;
  if (questions.isError) return <ErrorState error={questions.error} />;
  const qs = questions.data!;
  const current = steps[step];
  const applicable = qs.filter((q) => isApplicable(q, answers));
  const answered = applicable.filter((q) => answers[q.key] !== undefined).length;
  const profileErrors = {
    company_name: !profile.company_name ? "Company name is required" : undefined,
    contact_email: profile.contact_email && !/^\S+@\S+\.\S+$/.test(profile.contact_email) ? "Enter a valid email" : undefined,
    objectives: !(profile.objectives?.length) ? "Choose at least one objective" : undefined,
  };
  const stepMissing = current === "profile" ? Object.values(profileErrors).filter(Boolean) as string[] :
    current === "review" ? [] : missingInStep(qs, answers, current);

  const go = (n: number) => {
    if (n > step && stepMissing.length) { setShowErrors(true); return; }
    setShowErrors(false);
    setStep(n);
    save.mutate(n);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const setAnswer = (key: string, value: any) => setAnswers((prev) => {
    const next = { ...prev, [key]: value };
    // clear answers to conditional questions that no longer apply
    for (const q of qs) if (q.condition && !isApplicable(q, next)) delete next[q.key];
    return next;
  });

  return (
    <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
      <aside className="space-y-3">
        <div>
          <p className="text-xs text-muted-foreground">{answered} of {applicable.length} questions answered</p>
          <Progress value={(answered / Math.max(1, applicable.length)) * 100} className="mt-2" />
        </div>
        <ol className="flex gap-1 overflow-x-auto lg:flex-col">
          {steps.map((s, i) => {
            const missing = s === "profile" || s === "review" ? 0 : missingInStep(qs, answers, s).length;
            return (
              <li key={s}>
                <button onClick={() => (i <= step ? go(i) : undefined)} disabled={i > step}
                  className={cn("flex w-full items-center gap-2 whitespace-nowrap rounded-md px-2 py-1.5 text-left text-sm cursor-pointer disabled:cursor-default",
                    i === step ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground hover:bg-muted")}>
                  {i < step && missing === 0 ? <CheckCircle2 className="size-4 text-success" /> : <span className="flex size-4 items-center justify-center text-xs">{i + 1}</span>}
                  {s === "profile" ? "Organisation" : s === "review" ? "Review & submit" : dims[s]?.label ?? s}
                </button>
              </li>
            );
          })}
        </ol>
        <p className="text-xs text-muted-foreground"><Save className="mr-1 inline size-3" />Progress saves automatically when you move between steps.</p>
      </aside>

      <Card>
        <CardHeader>
          <CardTitle>{current === "profile" ? "About your organisation" : current === "review" ? "Review and submit" : dims[current]?.label}</CardTitle>
          <CardDescription>{current === "profile" ? "This personalises your report and opportunity estimates." :
            current === "review" ? "Scores are calculated deterministically by the server from your answers." : dims[current]?.summary}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {current === "profile" && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Company name" htmlFor="company_name" error={showErrors ? profileErrors.company_name : undefined}>
                <Input id="company_name" value={profile.company_name ?? ""} onChange={(e) => setProfile({ ...profile, company_name: e.target.value })} />
              </Field>
              <Field label="Industry" htmlFor="industry">
                <Input id="industry" value={profile.industry ?? ""} onChange={(e) => setProfile({ ...profile, industry: e.target.value })} />
              </Field>
              <Field label="Company size" htmlFor="company_size">
                <Select id="company_size" value={profile.company_size ?? ""} onChange={(e) => setProfile({ ...profile, company_size: e.target.value })}>
                  <option value="">Select…</option>{SIZES.map((s) => <option key={s}>{s}</option>)}
                </Select>
              </Field>
              <Field label="Website" htmlFor="website">
                <Input id="website" value={profile.website ?? ""} onChange={(e) => setProfile({ ...profile, website: e.target.value })} />
              </Field>
              <Field label="Contact name" htmlFor="contact_name">
                <Input id="contact_name" value={profile.contact_name ?? ""} onChange={(e) => setProfile({ ...profile, contact_name: e.target.value })} />
              </Field>
              <Field label="Contact email" htmlFor="contact_email" error={showErrors ? profileErrors.contact_email : undefined}>
                <Input id="contact_email" type="email" value={profile.contact_email ?? ""} onChange={(e) => setProfile({ ...profile, contact_email: e.target.value })} />
              </Field>
              <div className="sm:col-span-2">
                <Field label="Business objectives" error={showErrors ? profileErrors.objectives : undefined}>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {Object.entries(meta.data?.objectives ?? {}).map(([k, v]) => {
                      const checked = (profile.objectives ?? []).includes(k);
                      return (
                        <label key={k} className={cn("flex cursor-pointer items-center gap-2 rounded-lg border p-3 text-sm", checked && "border-primary bg-accent/50")}>
                          <input type="checkbox" checked={checked} onChange={() => setProfile({ ...profile,
                            objectives: checked ? profile.objectives.filter((o: string) => o !== k) : [...(profile.objectives ?? []), k] })} />
                          {v as string}
                        </label>
                      );
                    })}
                  </div>
                </Field>
              </div>
              <div className="sm:col-span-2">
                <Field label="The main business problem you want AI to help with" htmlFor="business_problem">
                  <Textarea id="business_problem" value={profile.business_problem ?? ""} onChange={(e) => setProfile({ ...profile, business_problem: e.target.value })} />
                </Field>
              </div>
            </div>
          )}

          {current !== "profile" && current !== "review" && qs.filter((q) => q.dimension === current && isApplicable(q, answers)).map((q, idx) => {
            const missing = showErrors && stepMissing.includes(q.key);
            return (
              <fieldset key={q.key} className={cn("space-y-3 rounded-lg p-1", missing && "ring-2 ring-danger/40")}>
                <legend className="font-medium">{idx + 1}. {q.text}</legend>
                {q.help_text && <p className="text-xs text-muted-foreground">{q.help_text}</p>}
                {q.condition && <Badge tone="primary">Follow-up question</Badge>}
                <div className={cn("grid gap-2", q.qtype === "scale" ? "grid-cols-5" : "sm:grid-cols-2")}>
                  {q.options.map((o) => {
                    const multi = q.qtype === "multi";
                    const selected = multi ? (answers[q.key] ?? []).includes(o.value) : answers[q.key] === o.value;
                    return (
                      <label key={o.value} className={cn("flex cursor-pointer items-center gap-2 rounded-lg border p-3 text-sm transition",
                        selected ? "border-primary bg-accent/60" : "hover:bg-muted", q.qtype === "scale" && "justify-center")}>
                        <input type={multi ? "checkbox" : "radio"} name={q.key} className={q.qtype === "scale" ? "sr-only" : ""} checked={selected}
                          onChange={() => setAnswer(q.key, multi ? (selected ? answers[q.key].filter((v: string) => v !== o.value) : [...(answers[q.key] ?? []), o.value]) : o.value)} />
                        {o.label}
                      </label>
                    );
                  })}
                </div>
                {missing && <p className="text-xs text-danger">Please answer this question.</p>}
              </fieldset>
            );
          })}

          {current === "review" && (
            <div className="space-y-4">
              {steps.filter((s) => s !== "profile" && s !== "review").map((s) => {
                const m = missingInStep(qs, answers, s).length;
                return (
                  <div key={s} className="flex items-center justify-between rounded-lg border p-3 text-sm">
                    <span>{dims[s]?.label}</span>
                    {m ? <Badge tone="warning">{m} unanswered</Badge> : <Badge tone="success">Complete</Badge>}
                  </div>
                );
              })}
              <p className="text-sm text-muted-foreground">After submission your answers are locked, your readiness score is calculated, and an AI-assisted narrative report is generated.</p>
            </div>
          )}

          {showErrors && stepMissing.length > 0 && (
            <p className="rounded-md bg-danger/10 p-3 text-sm text-danger" role="alert">Please complete the highlighted fields before continuing.</p>
          )}
          <div className="flex items-center justify-between border-t pt-4">
            <Button variant="outline" onClick={() => go(step - 1)} disabled={step === 0}><ChevronLeft /> Back</Button>
            {current === "review" ? (
              <Button onClick={() => submit.mutate()} loading={submit.isPending}
                disabled={steps.some((s) => s !== "profile" && s !== "review" && missingInStep(qs, answers, s).length > 0)}>
                Submit assessment
              </Button>
            ) : (
              <Button onClick={() => go(step + 1)} loading={save.isPending}>Continue <ChevronRight /></Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function scoreTone(s: number) {
  return s >= 65 ? "success" : s >= 45 ? "primary" : s >= 25 ? "warning" : "danger";
}

export function AssessmentReport({ id, canRegenerate }: { id: string; canRegenerate?: boolean }) {
  const qc = useQueryClient();
  const r = useQuery({ queryKey: ["report", id], queryFn: () => api(`/assessments/${id}/report`),
    refetchInterval: (q) => (q.state.data?.assessment?.report_status === "pending" ? 2000 : false) });
  const regen = useMutation({ mutationFn: () => api(`/assessments/${id}/report/regenerate`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["report", id] }), onError: (e) => toast.error(errorMessage(e)) });
  if (r.isPending) return <Loading rows={6} />;
  if (r.isError) return <ErrorState error={r.error} retry={() => r.refetch()} />;
  const { assessment, scores, findings, report, opportunities } = r.data;
  const radar = scores.map((s: any) => ({ dimension: s.dimension === "governance" ? "Governance" : s.dimension.charAt(0).toUpperCase() + s.dimension.slice(1), score: Number(s.score) }));
  const name = assessment.profile?.company_name ?? "organisation";

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <Card>
          <CardContent className="space-y-4 p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Overall AI readiness</p>
                <p className="text-5xl font-semibold tracking-tight">{Number(assessment.overall_score).toFixed(1)}<span className="text-xl text-muted-foreground">/100</span></p>
              </div>
              <Badge tone={scoreTone(assessment.overall_score)} className="text-sm">{assessment.classification}</Badge>
            </div>
            <p className="text-sm text-muted-foreground">{findings.classification_text}</p>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => downloadFile(`/assessments/${id}/report.pdf`, `ai-readiness-${name}.pdf`).catch((e) => toast.error(errorMessage(e)))}>
                <Download /> PDF report
              </Button>
              {canRegenerate && <Button variant="ghost" size="sm" onClick={() => regen.mutate()} loading={regen.isPending}><RefreshCw /> Regenerate narrative</Button>}
            </div>
            <p className="text-xs text-muted-foreground">{findings.method}. The AI narrative never changes scores.</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="h-72 p-4">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radar} outerRadius="72%">
                <PolarGrid stroke={CHART.grid} />
                <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 11 }} />
                <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
                <Radar isAnimationActive={false} dataKey="score" stroke={CHART.primary} fill={CHART.primary} fillOpacity={0.25} />
              </RadarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {assessment.report_status === "pending" && <p className="text-sm text-muted-foreground">Generating narrative report…</p>}
      {assessment.report_status === "failed" && <ErrorState error={new Error(report.error ?? "Narrative generation failed")} retry={canRegenerate ? () => regen.mutate() : undefined} />}
      {report.executive_summary && (
        <Card>
          <CardHeader><CardTitle>Executive summary</CardTitle><AiDraftNotice provenance={report.provenance}>AI-written explanation of deterministic results.</AiDraftNotice></CardHeader>
          <CardContent className="space-y-3 text-sm leading-relaxed">
            <p>{report.executive_summary}</p>
            <p className="font-medium">{report.key_message}</p>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {scores.map((s: any) => (
          <Card key={s.dimension}>
            <CardContent className="space-y-3 p-5">
              <div className="flex items-center justify-between">
                <p className="font-medium capitalize">{s.dimension === "data" ? "Data readiness" : s.dimension}</p>
                <Badge tone={scoreTone(Number(s.score))}>{s.level}</Badge>
              </div>
              <div className="flex items-end gap-2"><span className="text-2xl font-semibold">{Number(s.score).toFixed(1)}</span><span className="pb-1 text-xs text-muted-foreground">weight {(Number(s.weight) * 100).toFixed(0)}%</span></div>
              <Progress value={Number(s.score)} tone={scoreTone(Number(s.score)) as any} />
              {report.dimension_commentary?.[s.dimension] && <p className="text-xs text-muted-foreground">{report.dimension_commentary[s.dimension]}</p>}
              <details className="text-xs">
                <summary className="cursor-pointer text-primary">How this was scored</summary>
                <ul className="mt-2 space-y-1">
                  {s.breakdown.map((b: any) => (
                    <li key={b.key} className="flex justify-between gap-2"><span className="text-muted-foreground">{b.answer_label}</span><span className="shrink-0 font-mono">{b.score}/{b.max_score} × {b.weight}</span></li>
                  ))}
                </ul>
              </details>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <FindingList title="Strengths" items={findings.strengths.map((s: any) => s.title)} tone="success" />
        <FindingList title="Weaknesses" items={findings.weaknesses.map((s: any) => s.title)} tone="warning" />
        <FindingList title="Risks" items={findings.risks.map((r: any) => `${r.risk}`)} tone="danger" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Recommended first AI project</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p className="text-lg font-semibold text-primary">{findings.first_project?.title ?? "—"}</p>
            <p className="text-muted-foreground">{report.first_project_rationale}</p>
            <ul className="list-disc space-y-1 pl-5">
              {(findings.recommendations ?? []).map((r: any) => <li key={r.dimension}><strong>{r.label}:</strong> {r.recommendation}</li>)}
              {(report.adoption_recommendations ?? []).map((r: string) => <li key={r}>{r}</li>)}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>30 / 60 / 90 day plan</CardTitle></CardHeader>
          <CardContent className="space-y-4 text-sm">
            {(findings.plan_30_60_90 ?? []).map((w: any) => (
              <div key={w.window}><p className="font-medium">{w.window} · <span className="text-muted-foreground">{w.focus}</span></p>
                <ul className="mt-1 list-disc pl-5 text-muted-foreground">{w.actions.map((a: string) => <li key={a}>{a}</li>)}</ul></div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Implementation roadmap</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          {(findings.roadmap ?? []).map((r: any) => (
            <div key={r.horizon} className="rounded-lg border p-4">
              <Badge tone="primary">{r.horizon}</Badge>
              <p className="mt-2 font-medium">{r.milestone}</p>
              <ul className="mt-2 list-disc pl-5 text-sm text-muted-foreground">{r.outcomes.map((o: string) => <li key={o}>{o}</li>)}</ul>
            </div>
          ))}
        </CardContent>
      </Card>

      <OpportunityTable opportunities={opportunities} summary={report.opportunity_summary} />
    </div>
  );
}

function FindingList({ title, items, tone }: { title: string; items: string[]; tone: "success" | "warning" | "danger" }) {
  const Icon = tone === "success" ? CheckCircle2 : AlertTriangle;
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent>
        {items.length === 0 ? <p className="text-sm text-muted-foreground">None identified.</p> : (
          <ul className="space-y-2 text-sm">
            {items.map((i) => <li key={i} className="flex gap-2"><Icon className={cn("mt-0.5 size-4 shrink-0", tone === "success" ? "text-success" : tone === "warning" ? "text-warning" : "text-danger")} />{i}</li>)}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function OpportunityTable({ opportunities, summary }: { opportunities: any[]; summary?: string }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Prioritised AI opportunities</CardTitle>
        <CardDescription>Ranked by a configurable, deterministic formula. Financial values are illustrative estimates, not guaranteed outcomes.</CardDescription>
        {summary && <p className="text-sm">{summary}</p>}
      </CardHeader>
      <CardContent className="space-y-2">
        {opportunities.map((o) => (
          <div key={o.id} className="rounded-lg border">
            <button className="flex w-full flex-wrap items-center gap-3 p-3 text-left cursor-pointer" onClick={() => setOpen(open === o.id ? null : o.id)} aria-expanded={open === o.id}>
              <span className="flex size-7 items-center justify-center rounded-full bg-accent text-sm font-semibold text-accent-foreground">{o.rank}</span>
              <span className="flex-1 font-medium">{o.title}</span>
              <StatusBadge status={o.status} />
              <span className="font-mono text-sm">{Number(o.priority_score).toFixed(1)}</span>
            </button>
            {open === o.id && (
              <div className="grid gap-4 border-t p-4 text-sm md:grid-cols-2">
                <div className="space-y-2">
                  <p className="text-muted-foreground">{o.description}</p>
                  {o.narrative && <p>{o.narrative}</p>}
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    {[["Impact", o.business_impact], ["Complexity", o.implementation_complexity], ["Effort", `${o.effort_weeks} wks`],
                      ["Data availability", o.data_availability], ["Integration", o.integration_complexity], ["Security risk", o.security_risk]].map(([k, v]) => (
                      <div key={k as string} className="rounded-md bg-muted p-2"><p className="text-muted-foreground">{k}</p><p className="font-semibold">{v}{typeof v === "number" ? "/5" : ""}</p></div>
                    ))}
                  </div>
                </div>
                <div className="space-y-2">
                  <p className="font-medium">Reasoning</p>
                  <ul className="list-disc pl-5 text-xs text-muted-foreground">{o.reasoning.adjustments.map((a: string) => <li key={a}>{a}</li>)}</ul>
                  <p className="font-medium">ROI estimate <Badge tone="warning">Estimate</Badge></p>
                  <p className="text-xs">{money(o.roi_assumptions.estimated_annual_value_low, o.roi_assumptions.currency)} – {money(o.roi_assumptions.estimated_annual_value_high, o.roi_assumptions.currency)} / year ·
                    build {money(o.roi_assumptions.estimated_build_cost, o.roi_assumptions.currency)} · payback ~{o.roi_assumptions.estimated_payback_months ?? "—"} months</p>
                  <details className="text-xs"><summary className="cursor-pointer text-primary">Assumptions</summary>
                    <ul className="mt-1 space-y-0.5">{Object.entries(o.roi_assumptions.assumptions).map(([k, v]) => <li key={k}>{k.replace(/_/g, " ")}: <span className="font-mono">{String(v)}</span></li>)}</ul>
                  </details>
                </div>
              </div>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function StartAssessmentButton({ orgId, base }: { orgId?: string; base: string }) {
  const router = useRouter();
  const m = useMutation({ mutationFn: () => api("/assessments", { method: "POST", body: orgId ? { organisation_id: orgId } : {} }),
    onSuccess: (a) => router.push(`${base}/${a.id}`), onError: (e) => toast.error(errorMessage(e)) });
  return <Button onClick={() => m.mutate()} loading={m.isPending}>Start new assessment</Button>;
}
