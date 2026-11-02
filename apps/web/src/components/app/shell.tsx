"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity, Bell, Bot, Boxes, Briefcase, Building2, ClipboardCheck, DollarSign, FileText, FlaskConical, Gauge, LayoutDashboard,
  LifeBuoy, Lightbulb, LogOut, Menu, Moon, Network, PlugZap, Rocket, ScrollText, Search, Settings, ShieldAlert, Sun, Users, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { MockBanner } from "@/components/app/common";
import { LogoMark } from "@/components/site/logo";
import { Button, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, relativeTime } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: React.ComponentType<{ className?: string }>; perm?: string };

export const INTERNAL_NAV: { group: string; items: NavItem[] }[] = [
  { group: "", items: [{ href: "/app", label: "Overview", icon: LayoutDashboard }, { href: "/app/organisations", label: "Organisations", icon: Building2 }] },
  { group: "Assess", items: [
    { href: "/app/crm", label: "CRM", icon: Users, perm: "crm.read" },
    { href: "/app/assessments", label: "Assessments", icon: Gauge },
    { href: "/app/opportunities", label: "Opportunities", icon: Lightbulb } ] },
  { group: "Build", items: [
    { href: "/app/discovery", label: "Discovery", icon: Search, perm: "discovery.read" },
    { href: "/app/architecture", label: "Solution Design", icon: Network },
    { href: "/app/proposals", label: "Proposals", icon: FileText },
    { href: "/app/projects", label: "Projects", icon: Briefcase },
    { href: "/app/apps", label: "AI Applications", icon: Bot },
    { href: "/app/integrations", label: "Integrations", icon: PlugZap, perm: "integration.read" } ] },
  { group: "Deploy & Run", items: [
    { href: "/app/deployments", label: "Deployments", icon: Rocket },
    { href: "/app/monitoring", label: "Monitoring", icon: Activity },
    { href: "/app/evaluations", label: "Evaluations", icon: FlaskConical },
    { href: "/app/incidents", label: "Incidents", icon: ShieldAlert },
    { href: "/app/support", label: "Support", icon: LifeBuoy },
    { href: "/app/costs", label: "Cost Management", icon: DollarSign, perm: "cost.read" } ] },
  { group: "Admin", items: [
    { href: "/app/audit", label: "Audit Logs", icon: ScrollText, perm: "audit.read" },
    { href: "/app/settings", label: "Settings", icon: Settings } ] },
];

export const PORTAL_NAV: { group: string; items: NavItem[] }[] = [
  { group: "", items: [
    { href: "/portal", label: "Overview", icon: LayoutDashboard },
    { href: "/portal/assessments", label: "Assessments", icon: Gauge },
    { href: "/portal/opportunities", label: "Opportunities", icon: Lightbulb },
    { href: "/portal/proposals", label: "Proposals", icon: FileText },
    { href: "/portal/projects", label: "Projects", icon: Briefcase },
    { href: "/portal/assistant", label: "AI Assistant", icon: Bot },
    { href: "/portal/support", label: "Support", icon: LifeBuoy },
    { href: "/portal/incidents", label: "Incident updates", icon: ClipboardCheck },
    { href: "/portal/organisation", label: "Organisation", icon: Boxes } ] },
];

function useDarkMode() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    try { setDark(localStorage.getItem("dm-theme") === "dark"); } catch { /* storage unavailable */ }
  }, []);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try { localStorage.setItem("dm-theme", dark ? "dark" : "light"); } catch { /* storage unavailable */ }
    return () => document.documentElement.classList.remove("dark");
  }, [dark]);
  return [dark, setDark] as const;
}

function Notifications() {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["notifications"], queryFn: () => api<any[]>("/notifications"), refetchInterval: 30_000 });
  const unread = (q.data ?? []).filter((n) => !n.read_at).length;
  const markRead = async (id: string) => {
    await api(`/notifications/${id}/read`, { method: "POST" });
    qc.invalidateQueries({ queryKey: ["notifications"] });
  };
  return (
    <div className="relative">
      <Button variant="ghost" size="icon" aria-label={`Notifications (${unread} unread)`} onClick={() => setOpen((v) => !v)}>
        <Bell />
        {unread > 0 && <span className="absolute right-1.5 top-1.5 flex size-4 items-center justify-center rounded-full bg-danger text-[10px] text-white">{unread}</span>}
      </Button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl border bg-card p-2 shadow-xl">
          <p className="px-2 py-1 text-xs font-medium text-muted-foreground">Notifications</p>
          <div className="max-h-96 overflow-y-auto">
            {(q.data ?? []).length === 0 && <p className="px-2 py-6 text-center text-sm text-muted-foreground">You are all caught up.</p>}
            {(q.data ?? []).map((n) => (
              <Link key={n.id} href={n.link ?? "#"} onClick={() => { markRead(n.id); setOpen(false); }}
                className={cn("block rounded-lg px-2 py-2 hover:bg-muted", !n.read_at && "bg-accent/50")}>
                <p className="text-sm font-medium">{n.title}</p>
                {n.body && <p className="line-clamp-2 text-xs text-muted-foreground">{n.body}</p>}
                <p className="mt-0.5 text-[11px] text-muted-foreground">{relativeTime(n.created_at)}</p>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function AppShell({ area, children }: { area: "internal" | "portal"; children: React.ReactNode }) {
  const { me, loading, logout, can, customerOrg } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [mobile, setMobile] = useState(false);
  const [dark, setDark] = useDarkMode();
  useEffect(() => {
    setMobile(false);
  }, [pathname]);

  useEffect(() => {
    if (loading) return;
    if (!me) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    else if (area === "internal" && !me.is_internal) router.replace("/portal");
    else if (area === "portal" && me.is_internal) router.replace("/app");
  }, [loading, me, area, router, pathname]);

  if (loading || !me || (area === "internal") !== me.is_internal) {
    return <div className="flex min-h-screen items-center justify-center"><Skeleton className="h-10 w-48" /></div>;
  }

  const nav = area === "internal" ? INTERNAL_NAV : PORTAL_NAV;
  const root = area === "internal" ? "/app" : "/portal";
  const sidebar = (
    <nav className="flex h-full flex-col gap-4 overflow-y-auto p-3" aria-label="Application">
      <Link href={root} className="flex items-center gap-2 px-2 py-1 font-semibold"><LogoMark className="size-6" /> DeployMind</Link>
      {nav.map((g) => {
        const items = g.items.filter((i) => !i.perm || can(i.perm));
        if (!items.length) return null;
        return (
          <div key={g.group || "main"} className="space-y-0.5">
            {g.group && <p className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{g.group}</p>}
            {items.map((i) => {
              const active = i.href === root ? pathname === root : pathname.startsWith(i.href);
              return (
                <Link key={i.href} href={i.href}
                  className={cn("flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition hover:bg-muted hover:text-foreground",
                    active && "bg-accent font-medium text-accent-foreground")}>
                  <i.icon className="size-4" />{i.label}
                </Link>
              );
            })}
          </div>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen bg-muted/30">
      <MockBanner show={me.mock_ai} />
      <div className="flex">
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 border-r bg-card lg:block">{sidebar}</aside>
        {mobile && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <div className="absolute inset-0 bg-black/40" onClick={() => setMobile(false)} />
            <aside className="absolute inset-y-0 left-0 w-64 border-r bg-card">{sidebar}</aside>
          </div>
        )}
        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-card/90 px-4 backdrop-blur">
            <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobile((v) => !v)} aria-label="Toggle navigation">
              {mobile ? <X /> : <Menu />}
            </Button>
            <div className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
              {area === "internal" ? <>DeployMind · <span className="text-foreground">{me.internal_role?.replace("_", " ")}</span></> :
                <span className="text-foreground">{customerOrg?.organisation_name}</span>}
            </div>
            <Notifications />
            <Button variant="ghost" size="icon" onClick={() => setDark(!dark)} aria-label="Toggle dark theme">{dark ? <Sun /> : <Moon />}</Button>
            <div className="hidden text-right text-xs sm:block">
              <p className="font-medium text-foreground">{me.full_name}</p>
              <p className="text-muted-foreground">{me.email}</p>
            </div>
            <Button variant="ghost" size="icon" onClick={logout} aria-label="Sign out"><LogOut /></Button>
          </header>
          <main className="mx-auto w-full max-w-[1400px] p-4 sm:p-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
