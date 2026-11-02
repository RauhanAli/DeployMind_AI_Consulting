"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, refreshAccessToken, setAccessToken } from "@/lib/api";

export type Membership = {
  organisation_id: string;
  organisation_name: string;
  organisation_slug: string;
  kind: "provider" | "customer";
  role: string;
  permissions: string[];
};

export type Me = {
  id: string;
  email: string;
  full_name: string;
  is_internal: boolean;
  internal_role: string | null;
  memberships: Membership[];
  mock_ai: boolean;
  ai_provider: string;
};

type AuthCtx = {
  me: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<Me>;
  register: (body: Record<string, unknown>) => Promise<Me>;
  logout: () => Promise<void>;
  can: (perm: string) => boolean;
  customerOrg: Membership | null;
  reload: () => Promise<void>;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const qc = useQueryClient();
  const router = useRouter();

  const loadMe = useCallback(async () => {
    const m = await api<Me>("/auth/me");
    setMe(m);
    return m;
  }, []);

  useEffect(() => {
    (async () => {
      const t = await refreshAccessToken();
      if (t) {
        try {
          await loadMe();
        } catch {
          setMe(null);
        }
      }
      setLoading(false);
    })();
  }, [loadMe]);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api<{ access_token: string }>("/auth/login", { method: "POST", body: { email, password } });
    setAccessToken(r.access_token);
    qc.clear();
    return loadMe();
  }, [loadMe, qc]);

  const register = useCallback(async (body: Record<string, unknown>) => {
    const r = await api<{ access_token: string }>("/auth/register", { method: "POST", body });
    setAccessToken(r.access_token);
    qc.clear();
    return loadMe();
  }, [loadMe, qc]);

  const logout = useCallback(async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    setAccessToken(null);
    setMe(null);
    qc.clear();
    router.push("/login");
  }, [qc, router]);

  const value = useMemo<AuthCtx>(() => {
    const customerOrg = me?.memberships.find((m) => m.kind === "customer") ?? null;
    const perms = new Set(me?.memberships.flatMap((m) => m.permissions) ?? []);
    return { me, loading, login, register, logout, reload: async () => void (await loadMe()),
      can: (p: string) => perms.has(p), customerOrg };
  }, [me, loading, login, register, logout, loadMe]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}

export const homeFor = (me: Me) => (me.is_internal ? "/app" : "/portal");
