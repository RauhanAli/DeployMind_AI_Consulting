import type { Metadata } from "next";

import { CtaBand, SectionHeading } from "@/components/site/chrome";
import { Badge, Card, CardContent } from "@/components/ui";
import { USE_CASES } from "@/lib/content";

export const metadata: Metadata = { title: "AI use cases" };

export default function UseCasesPage() {
  return (
    <>
      <section className="container-page py-16 md:py-20">
        <SectionHeading as="h1" eyebrow="Use cases" title="Practical AI, matched to real workflows"
          intro="The readiness assessment ranks these against your data, systems and risk profile so you start where value is most likely." />
        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {USE_CASES.map((u) => (
            <Card key={u.title}><CardContent className="space-y-3 p-6">
              <Badge>{u.industry}</Badge><h2 className="font-semibold">{u.title}</h2><p className="text-sm text-muted-foreground">{u.body}</p>
            </CardContent></Card>
          ))}
        </div>
      </section>
      <CtaBand title="Not sure which use case fits?" body="The free readiness assessment ranks seven common opportunities for your organisation." />
    </>
  );
}
