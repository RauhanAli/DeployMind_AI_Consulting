import type { Metadata } from "next";

import { CtaBand, SectionHeading } from "@/components/site/chrome";
import { Card, CardContent } from "@/components/ui";
import { CASE_STUDIES } from "@/lib/content";

export const metadata: Metadata = { title: "Case studies" };

export default function CaseStudiesPage() {
  return (
    <>
      <section className="container-page py-16 md:py-20">
        <SectionHeading as="h1" eyebrow="Case studies" title="How engagements unfold"
          intro="These are synthetic examples that illustrate our delivery approach. Organisations are fictional and figures are illustrative." />
        <div className="mt-12 space-y-6">
          {CASE_STUDIES.map((c) => (
            <Card key={c.slug} id={c.slug}>
              <CardContent className="grid gap-6 p-6 md:grid-cols-[1.4fr_1fr] md:p-8">
                <div className="space-y-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{c.client}</p>
                  <h2 className="text-2xl font-semibold tracking-tight">{c.title}</h2>
                  <div><h3 className="text-sm font-semibold">Challenge</h3><p className="text-muted-foreground">{c.challenge}</p></div>
                  <div><h3 className="text-sm font-semibold">Solution</h3><p className="text-muted-foreground">{c.solution}</p></div>
                </div>
                <div className="grid content-start gap-3">
                  {c.results.map(([v, l]) => (
                    <div key={l} className="rounded-lg border bg-muted/40 p-4">
                      <div className="text-2xl font-semibold text-primary">{v}</div><div className="text-sm text-muted-foreground">{l}</div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
      <CtaBand />
    </>
  );
}
