import type { Metadata } from "next";

import { CtaBand, SectionHeading } from "@/components/site/chrome";
import { Card, CardContent } from "@/components/ui";

export const metadata: Metadata = { title: "About" };

const VALUES = [
  ["Own the outcome", "We stay accountable after go-live: monitoring, evaluation, incidents and support are part of the job."],
  ["Deterministic where it matters", "AI drafts and explains. Code decides scores, permissions, money and state transitions."],
  ["Honest numbers", "Estimates are labelled as estimates. Demo telemetry is never presented as production data."],
  ["Security by default", "Tenant isolation, least-privilege access, encrypted credentials and full audit trails."],
];

export default function AboutPage() {
  return (
    <>
      <section className="container-page py-16 md:py-20">
        <SectionHeading as="h1" eyebrow="About DeployMind" title="Forward deployed engineers for enterprise AI"
          intro="DeployMind exists for the gap between a promising AI demo and a system a business can depend on. We embed with customer teams, understand the operational constraints, and take responsibility for getting AI into production — and keeping it there." />
        <div className="mt-12 grid gap-5 sm:grid-cols-2">
          {VALUES.map(([t, b]) => (
            <Card key={t}><CardContent className="space-y-2 p-6"><h2 className="font-semibold">{t}</h2><p className="text-sm text-muted-foreground">{b}</p></CardContent></Card>
          ))}
        </div>
        <p className="mt-10 max-w-2xl text-sm text-muted-foreground">
          This site and platform are an end-to-end demonstration of the forward deployed engineering workflow. Customer names and
          case studies are fictional.
        </p>
      </section>
      <CtaBand />
    </>
  );
}
