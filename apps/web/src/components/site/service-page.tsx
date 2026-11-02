import { CheckCircle2 } from "lucide-react";
import Link from "next/link";

import { CtaBand, SectionHeading } from "@/components/site/chrome";
import { Button, Card, CardContent } from "@/components/ui";
import { SERVICES } from "@/lib/content";
import { ICONS } from "@/lib/icons";

export function ServicePage({ slug }: { slug: string }) {
  const s = SERVICES.find((x) => x.slug === slug)!;
  const Icon = ICONS[s.icon as keyof typeof ICONS];
  const others = SERVICES.filter((x) => x.slug !== slug).slice(0, 3);
  return (
    <>
      <section className="border-b bg-gradient-to-b from-accent/50 to-background">
        <div className="container-page grid gap-10 py-16 md:grid-cols-[1.4fr_1fr] md:py-24">
          <div className="space-y-6 fade-up">
            <span className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-sm text-muted-foreground">
              <Icon className="size-4 text-primary" /> {s.name}
            </span>
            <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">{s.headline}</h1>
            <p className="max-w-xl text-lg text-muted-foreground">{s.intro}</p>
            <div className="flex flex-wrap gap-3">
              <Button asChild size="lg"><Link href={s.cta.href}>{s.cta.label}</Link></Button>
              <Button asChild size="lg" variant="outline"><Link href="/contact">Ask a question</Link></Button>
            </div>
          </div>
          <Card className="self-start fade-up">
            <CardContent className="space-y-4 p-6">
              <h2 className="font-semibold">What you get</h2>
              <ul className="space-y-3">
                {s.outcomes.map((o) => (
                  <li key={o} className="flex gap-2 text-sm"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />{o}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      </section>
      <section className="container-page py-16">
        <SectionHeading eyebrow="Approach" title="How we work" />
        <div className="mt-10 grid gap-6 md:grid-cols-3">
          {s.approach.map((a, i) => (
            <Card key={a.title}>
              <CardContent className="space-y-2 p-6">
                <span className="text-sm font-semibold text-primary">0{i + 1}</span>
                <h3 className="text-lg font-semibold">{a.title}</h3>
                <p className="text-sm text-muted-foreground">{a.body}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
      <section className="border-y bg-muted/40">
        <div className="container-page grid gap-10 py-16 md:grid-cols-2">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Deliverables</h2>
            <ul className="mt-5 space-y-3">
              {s.deliverables.map((d) => <li key={d} className="flex gap-2"><CheckCircle2 className="mt-0.5 size-5 shrink-0 text-primary" />{d}</li>)}
            </ul>
          </div>
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">A good fit for</h2>
            <ul className="mt-5 space-y-3">
              {s.fit.map((d) => <li key={d} className="flex gap-2"><CheckCircle2 className="mt-0.5 size-5 shrink-0 text-primary" />{d}</li>)}
            </ul>
          </div>
        </div>
      </section>
      <section className="container-page py-16">
        <h2 className="text-xl font-semibold">Related services</h2>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {others.map((o) => (
            <Link key={o.slug} href={`/${o.slug}`} className="rounded-xl border bg-card p-5 transition hover:border-primary/40 hover:shadow-sm">
              <h3 className="font-semibold">{o.name}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{o.short}</p>
            </Link>
          ))}
        </div>
      </section>
      <CtaBand />
    </>
  );
}
