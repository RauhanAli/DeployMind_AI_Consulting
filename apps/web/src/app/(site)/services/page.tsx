import type { Metadata } from "next";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { CtaBand, SectionHeading } from "@/components/site/chrome";
import { SERVICES } from "@/lib/content";
import { ICONS } from "@/lib/icons";

export const metadata: Metadata = { title: "Services" };

export default function ServicesPage() {
  return (
    <>
      <section className="container-page py-16 md:py-20">
        <SectionHeading as="h1" eyebrow="Services" title="Assess, build and run enterprise AI"
          intro="Pick a starting point. Every engagement follows the same accountable delivery model and ends with a system you can operate." />
        <div className="mt-12 grid gap-5 md:grid-cols-2">
          {SERVICES.map((s) => {
            const Icon = ICONS[s.icon as keyof typeof ICONS];
            return (
              <Link key={s.slug} href={`/${s.slug}`} className="group flex gap-5 rounded-xl border bg-card p-6 transition hover:border-primary/40 hover:shadow-md">
                <span className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground"><Icon className="size-5" /></span>
                <div className="space-y-2">
                  <h2 className="text-lg font-semibold">{s.name}</h2>
                  <p className="text-sm text-muted-foreground">{s.intro}</p>
                  <span className="inline-flex items-center gap-1 text-sm font-medium text-primary">Explore <ArrowRight className="size-4" /></span>
                </div>
              </Link>
            );
          })}
        </div>
      </section>
      <CtaBand />
    </>
  );
}
