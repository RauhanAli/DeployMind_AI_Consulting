import type { Metadata } from "next";
import { CheckCircle2 } from "lucide-react";
import { Suspense } from "react";

import { SectionHeading } from "@/components/site/chrome";
import { ContactForm } from "@/components/site/forms";
import { Card, CardContent } from "@/components/ui";

export const metadata: Metadata = { title: "Book a discovery call" };

export default function BookPage() {
  return (
    <section className="container-page grid gap-12 py-16 md:grid-cols-[1fr_1.2fr] md:py-20">
      <div className="space-y-6">
        <SectionHeading as="h1" eyebrow="Discovery call" title="30 minutes with a forward deployed engineer"
          intro="Bring a business problem or a prototype. Leave with a clear view of feasibility, risks and next steps." />
        <ul className="space-y-3 text-sm">
          {["Understand your workflow, systems and constraints", "Identify data sources and integration needs",
            "Discuss security, compliance and success metrics", "Agree whether an assessment or pilot makes sense"].map((t) => (
            <li key={t} className="flex gap-2"><CheckCircle2 className="mt-0.5 size-4 text-success" />{t}</li>
          ))}
        </ul>
      </div>
      <Card><CardContent className="p-6"><Suspense><ContactForm kind="discovery" /></Suspense></CardContent></Card>
    </section>
  );
}
