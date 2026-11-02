"use client";

import { ChevronDown, Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Logo } from "@/components/site/logo";
import { Button } from "@/components/ui";
import { homeFor, useAuth } from "@/lib/auth";
import { SERVICES } from "@/lib/content";
import { ICONS } from "@/lib/icons";
import { cn } from "@/lib/utils";


const NAV = [
  { href: "/ai-readiness", label: "AI Readiness" },
  { href: "/use-cases", label: "Use cases" },
  { href: "/case-studies", label: "Case studies" },
  { href: "/about", label: "About" },
];

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const [menu, setMenu] = useState(false);
  const pathname = usePathname();
  const { me } = useAuth();
  useEffect(() => { setOpen(false); setMenu(false); }, [pathname]);

  return (
    <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur">
      <div className="container-page flex h-16 items-center justify-between gap-4">
        <Logo />
        <nav className="hidden items-center gap-1 lg:flex" aria-label="Main">
          <div className="relative" onMouseLeave={() => setMenu(false)}>
            <button
              className="flex items-center gap-1 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground cursor-pointer"
              onClick={() => setMenu((v) => !v)} onMouseEnter={() => setMenu(true)} aria-expanded={menu}
            >
              Services <ChevronDown className="size-4" />
            </button>
            {menu && (
              <div className="absolute left-0 top-full w-[560px] pt-2">
                <div className="grid grid-cols-2 gap-1 rounded-xl border bg-card p-2 shadow-lg">
                  {SERVICES.map((s) => {
                    const Icon = ICONS[s.icon as keyof typeof ICONS];
                    return (
                      <Link key={s.slug} href={`/${s.slug}`} className="flex gap-3 rounded-lg p-3 hover:bg-muted">
                        <Icon className="mt-0.5 size-5 text-primary" />
                        <span>
                          <span className="block text-sm font-medium">{s.name}</span>
                          <span className="block text-xs text-muted-foreground">{s.short}</span>
                        </span>
                      </Link>
                    );
                  })}
                  <Link href="/services" className="col-span-2 rounded-lg p-2 text-center text-sm font-medium text-primary hover:bg-muted">
                    All services →
                  </Link>
                </div>
              </div>
            )}
          </div>
          {NAV.map((n) => (
            <Link key={n.href} href={n.href}
              className={cn("rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground", pathname === n.href && "text-foreground")}>
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="hidden items-center gap-2 lg:flex">
          {me ? (
            <Button asChild size="sm"><Link href={homeFor(me)}>Open {me.is_internal ? "dashboard" : "portal"}</Link></Button>
          ) : (
            <>
              <Button asChild variant="ghost" size="sm"><Link href="/login">Sign in</Link></Button>
              <Button asChild size="sm"><Link href="/book-discovery-call">Book a discovery call</Link></Button>
            </>
          )}
        </div>
        <button className="rounded-md p-2 lg:hidden cursor-pointer" onClick={() => setOpen((v) => !v)} aria-label="Toggle menu" aria-expanded={open}>
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </div>
      {open && (
        <div className="border-t bg-background lg:hidden">
          <nav className="container-page flex flex-col gap-1 py-3" aria-label="Mobile">
            <Link href="/services" className="rounded-md px-2 py-2 font-medium">Services</Link>
            {SERVICES.map((s) => (
              <Link key={s.slug} href={`/${s.slug}`} className="rounded-md px-4 py-1.5 text-sm text-muted-foreground">{s.name}</Link>
            ))}
            {NAV.map((n) => <Link key={n.href} href={n.href} className="rounded-md px-2 py-2 font-medium">{n.label}</Link>)}
            <Link href="/contact" className="rounded-md px-2 py-2 font-medium">Contact</Link>
            <div className="mt-2 flex gap-2">
              {me ? <Button asChild className="flex-1"><Link href={homeFor(me)}>Open {me.is_internal ? "dashboard" : "portal"}</Link></Button> : (
                <>
                  <Button asChild variant="outline" className="flex-1"><Link href="/login">Sign in</Link></Button>
                  <Button asChild className="flex-1"><Link href="/book-discovery-call">Book a call</Link></Button>
                </>
              )}
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="border-t bg-muted/40">
      <div className="container-page grid gap-8 py-12 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-3">
          <Logo />
          <p className="text-sm text-muted-foreground">From AI prototype to production-ready enterprise systems. Assess, build, deploy and run.</p>
        </div>
        <div>
          <h4 className="mb-3 text-sm font-semibold">Services</h4>
          <ul className="space-y-2 text-sm text-muted-foreground">
            {SERVICES.slice(0, 5).map((s) => <li key={s.slug}><Link href={`/${s.slug}`} className="hover:text-foreground">{s.name}</Link></li>)}
          </ul>
        </div>
        <div>
          <h4 className="mb-3 text-sm font-semibold">Company</h4>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><Link href="/about" className="hover:text-foreground">About</Link></li>
            <li><Link href="/case-studies" className="hover:text-foreground">Case studies</Link></li>
            <li><Link href="/use-cases" className="hover:text-foreground">Use cases</Link></li>
            <li><Link href="/contact" className="hover:text-foreground">Contact</Link></li>
          </ul>
        </div>
        <div>
          <h4 className="mb-3 text-sm font-semibold">Get started</h4>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><Link href="/ai-readiness" className="hover:text-foreground">Take the AI readiness assessment</Link></li>
            <li><Link href="/book-discovery-call" className="hover:text-foreground">Book a discovery call</Link></li>
            <li><Link href="/login" className="hover:text-foreground">Client portal sign-in</Link></li>
          </ul>
        </div>
      </div>
      <div className="border-t">
        <div className="container-page flex flex-col gap-2 py-5 text-xs text-muted-foreground sm:flex-row sm:justify-between">
          <span>© {new Date().getFullYear()} DeployMind. A demonstration platform — case studies are synthetic and metrics illustrative.</span>
          <span>Built with Next.js, FastAPI, PostgreSQL + pgvector.</span>
        </div>
      </div>
    </footer>
  );
}

export function SectionHeading({ eyebrow, title, intro, center, as: Tag = "h2" }: { eyebrow?: string; title: string; intro?: string; center?: boolean; as?: "h1" | "h2" }) {
  return (
    <div className={cn("max-w-2xl space-y-3", center && "mx-auto text-center")}>
      {eyebrow && <p className="text-sm font-semibold uppercase tracking-wider text-primary">{eyebrow}</p>}
      <Tag className="text-3xl font-semibold tracking-tight sm:text-4xl">{title}</Tag>
      {intro && <p className="text-lg text-muted-foreground">{intro}</p>}
    </div>
  );
}

export function CtaBand({ title = "Have an AI idea or a stuck prototype?", body = "Book a 30-minute discovery call with a forward deployed engineer." }: { title?: string; body?: string }) {
  return (
    <section className="container-page py-16">
      <div className="flex flex-col items-start gap-6 rounded-2xl bg-primary px-6 py-10 text-primary-foreground sm:px-10 md:flex-row md:items-center md:justify-between">
        <div className="space-y-2">
          <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
          <p className="text-primary-foreground/80">{body}</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button asChild variant="secondary" size="lg"><Link href="/book-discovery-call">Book a discovery call</Link></Button>
          <Button asChild variant="outline" size="lg" className="border-white/30 bg-transparent text-white hover:bg-white/10">
            <Link href="/ai-readiness">Assess readiness</Link>
          </Button>
        </div>
      </div>
    </section>
  );
}
